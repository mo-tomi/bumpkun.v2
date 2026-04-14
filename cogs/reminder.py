# cogs/reminder.py - 2段階リマインダー + リアルタイムカウントアップ

import discord
from discord.ext import commands, tasks
import datetime
import asyncio
import logging
import database as db


class ReminderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Cog読み込み時にタスクを開始"""
        if not self.reminder_task.is_running():
            self.reminder_task.start()
            logging.info("リマインダータスク開始")

    async def cog_unload(self):
        """Cog終了時にタスクを停止"""
        self.reminder_task.cancel()

    @tasks.loop(minutes=1)
    async def reminder_task(self):
        try:
            reminder = await db.get_reminder()
            if not reminder:
                return

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            remind_at = reminder['remind_at']
            channel_id = reminder['channel_id']
            status = reminder.get('status', 'waiting')

            if status == 'waiting' and now_utc >= remind_at:
                try:
                    channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                    if channel:
                        await channel.send("⏰ そろそろBumpの時間だよ！`/bump` をお願いします！")
                        logging.info(f"1st リマインダー送信: ch={channel_id}")
                        await db.update_reminder_status(channel_id, 'notified_1st')
                except Exception as e:
                    logging.error(f"1st リマインダー送信失敗: {e}")

            elif status == 'notified_1st' and now_utc >= (remind_at + datetime.timedelta(minutes=30)):
                try:
                    channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                    if channel:
                        elapsed = now_utc - remind_at
                        elapsed_str = _format_elapsed(elapsed)

                        text = (
                            f"前回のBumpから **{elapsed_str}** が経過しました。\n"
                            "サーバーの宣伝のため、お時間のある時にBumpをお願いいたします。🙇‍♂️"
                        )
                        sent = await channel.send(text)
                        logging.info(f"2nd リマインダー送信: ch={channel_id}")

                        # バックグラウンドでカウントアップ更新
                        asyncio.create_task(self._countdown_loop(sent, remind_at))
                        await db.clear_reminder()
                except Exception as e:
                    logging.error(f"2nd リマインダー送信失敗: {e}")

        except Exception as e:
            logging.error(f"リマインダータスクエラー: {e}", exc_info=True)

    @reminder_task.before_loop
    async def before_reminder_task(self):
        await self.bot.wait_until_ready()

    async def _countdown_loop(self, message: discord.Message, start_time: datetime.datetime):
        """メッセージをリアルタイムで更新してカウントアップを表示"""
        try:
            while True:
                await asyncio.sleep(60)
                try:
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    elapsed = now_utc - start_time

                    # 2時間経過で停止
                    if elapsed.total_seconds() >= 7200:
                        logging.info("カウントアップ: 2時間経過で停止")
                        break

                    elapsed_str = _format_elapsed(elapsed)
                    content = (
                        f"前回のBumpから **{elapsed_str}** が経過しました。\n"
                        "サーバーの宣伝のため、お時間のある時にBumpをお願いいたします。🙇‍♂️"
                    )
                    await message.edit(content=content)
                except discord.NotFound:
                    logging.info("カウントアップ: メッセージ削除で停止")
                    break
                except discord.Forbidden:
                    logging.warning("カウントアップ: 権限不足で停止")
                    break
                except Exception as e:
                    logging.error(f"カウントアップ更新エラー: {e}")
                    break
        except Exception as e:
            logging.error(f"カウントアップループエラー: {e}")


def _format_elapsed(td: datetime.timedelta) -> str:
    """timedeltaを「X時間Y分」形式の文字列に変換"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        return f"{hours}時間{minutes}分"
    return f"{minutes}分"


async def setup(bot: commands.Bot):
    await bot.add_cog(ReminderCog(bot))
