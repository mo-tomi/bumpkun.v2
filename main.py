# main.py - BUMPくん v3 エントリーポイント

import os
import signal
import sys
import asyncio
import threading
import logging
import discord
from discord.ext import commands
from flask import Flask

import database as db
from config import TOKEN, PORT

logging.basicConfig(level=logging.INFO)

# --- Cogの一覧 ---
COG_MODULES = [
    "cogs.bump",
    "cogs.ranking",
    "cogs.reminder",
    "cogs.admin",
]


# --- Bot本体 ---
class BumpkunBot(commands.Bot):
    async def setup_hook(self) -> None:
        """起動時に1回だけ実行される初期化処理"""
        try:
            await db.init_db()
            logging.info("DB初期化完了")

            for cog in COG_MODULES:
                await self.load_extension(cog)
                logging.info(f"Cog読み込み: {cog}")

            await self.tree.sync()
            logging.info("スラッシュコマンド同期完了")

        except Exception as e:
            logging.error(f"!!! 起動エラー: {e}", exc_info=True)


intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = BumpkunBot(command_prefix='/', intents=intents)


@bot.event
async def on_ready():
    logging.info(f"------\nBot起動完了: {bot.user.name}\n------")


@bot.event
async def on_disconnect():
    try:
        logging.info("Bot切断 - DBプール終了中...")
        await db.close_pool()
    except Exception as e:
        logging.error(f"切断時エラー: {e}")


# --- Webサーバー（スリープ対策） ---
app = Flask(__name__)


@app.route('/')
def index():
    return "BUMPくん v3 is running!", 200


@app.route('/health')
def health_check():
    return "OK", 200


def run_web_server():
    app.run(host='0.0.0.0', port=PORT)


# --- シグナルハンドラー ---
def signal_handler(sig, frame):
    logging.info("終了シグナル受信...")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_shutdown())
        else:
            asyncio.run(_shutdown())
    except Exception as e:
        logging.error(f"終了処理エラー: {e}")
    finally:
        sys.exit(0)


async def _shutdown():
    try:
        await db.close_pool()
        logging.info("DB終了完了")
    except Exception as e:
        logging.error(f"DB終了エラー: {e}")
    try:
        await bot.close()
        logging.info("Bot終了完了")
    except Exception as e:
        logging.error(f"Bot終了エラー: {e}")


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# --- 起動 ---
def main():
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    if TOKEN:
        try:
            bot.run(TOKEN)
        except KeyboardInterrupt:
            logging.info("Bot停止 (KeyboardInterrupt)")
        except Exception as e:
            logging.error(f"!!! FATAL: {e}", exc_info=True)
        finally:
            try:
                asyncio.run(db.close_pool())
                logging.info("最終クリーンアップ完了")
            except Exception as e:
                logging.error(f"最終クリーンアップエラー: {e}")
    else:
        logging.error("!!! FATAL: DISCORD_BOT_TOKEN が設定されていません")


if __name__ == "__main__":
    main()
