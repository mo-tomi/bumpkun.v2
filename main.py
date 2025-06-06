import discord
from discord.ext import commands, tasks
from discord import app_commands # app_commandsをインポート
import os
import re
import random
import datetime
import asyncio
import database as db
from flask import Flask
import threading
import logging

# --- ロギング設定 ---
logging.basicConfig(level=logging.INFO)

# --- 設定 ---
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
DISBOARD_BOT_ID = 302050872383242240

# --- Botの準備 ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix='/', intents=intents)

# --- Webサーバー（Renderスリープ対策）の準備 ---
app = Flask(__name__)
@app.route('/')
def index():
    return "Bot is running!", 200
@app.route('/health')
def health_check():
    return "OK", 200
def run_web_server():
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 10000))

# --- Botのイベント ---
@bot.event
async def on_ready():
    logging.info("Bot is preparing...")
    try:
        logging.info("Connecting to database...")
        pool = await db.get_pool()
        async with pool.acquire():
            logging.info("Database connection successful.")
        await pool.close()
        
        logging.info("Initializing database table...")
        await db.init_db()
        logging.info("Database table initialized.")
        
        if not reminder_task.is_running():
            reminder_task.start()
            logging.info("Reminder task started.")
        
        await bot.tree.sync()
        logging.info("Slash commands synchronized.")
        
        logging.info("------")
        logging.info(f'Bot started successfully: {bot.user.name}')
        logging.info("------")
    except Exception as e:
        logging.error(f"!!! CRITICAL ERROR ON STARTUP: {e}", exc_info=True)

@bot.event
async def on_message(message):
    if message.author.id == DISBOARD_BOT_ID and message.embeds:
        embed = message.embeds[0]
        if embed.description and "表示順をアップしたよ" in embed.description:
            logging.info("Bump success message detected.")
            match = re.search(r'<@!?(\d+)>', embed.description)
            if match:
                user_id = int(match.group(1))
                try:
                    count = await db.record_bump(user_id)
                    user = bot.get_user(user_id) or await bot.fetch_user(user_id)
                    logging.info(f"Record successful for {user.name} ({user_id}). Total bumps: {count}")
                    
                    thanks_messages = ["ありがとう！サーバーが盛り上がるね！", "ナイスBump！君はヒーローだ！", "サンキュー！次も頼んだよ！", "お疲れ様！ゆっくり休んでね！"]
                    await message.channel.send(f"{user.mention} {random.choice(thanks_messages)} (累計 **{count}** 回)")

                    if count in [10, 50, 100, 150, 200]:
                         await message.channel.send(f"🎉🎉Congratulation!!🎉🎉 {user.mention} なんと累計 **{count}回** のBumpを達成しました！本当にありがとう！")

                    remind_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
                    await db.set_reminder(message.channel.id, remind_time)
                    logging.info(f"Reminder set for {remind_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                except Exception as e:
                    logging.error(f"Error processing bump: {e}", exc_info=True)
                    await message.channel.send("おっと、Bumpの記録中にエラーが起きたみたい…ごめんね！")

# --- スラッシュコマンド ---
# (bump_top, bump_user, bump_time は変更なし)
@bot.tree.command(name="bump_top", description="Bump回数のトップ5ランキングを表示します。")
async def bump_top(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        top_users = await db.get_top_users()
        if not top_users:
            await interaction.followup.send("まだ誰もBumpしていません。まずは`/bump`してみよう！")
            return
        embed = discord.Embed(title="🏆 Bumpランキング 🏆", color=discord.Color.gold())
        rank_text = ""
        for i, record in enumerate(top_users):
            user = await bot.fetch_user(record['user_id'])
            rank_text += f"**{i+1}位**: {user.display_name} - **{record['bump_count']}** 回\n"
        embed.description = rank_text
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logging.error(f"Error in /bump_top: {e}", exc_info=True)
        await interaction.followup.send("ごめん！ランキングの表示中にエラーが起きました。")

@bot.tree.command(name="bump_user", description="指定したユーザーのBump回数を表示します。")
async def bump_user(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer()
    try:
        count = await db.get_user_count(user.id)
        await interaction.followup.send(f"{user.display_name}さんの累計Bump回数は **{count}回** です。")
    except Exception as e:
        logging.error(f"Error in /bump_user: {e}", exc_info=True)
        await interaction.followup.send("ごめん！回数の表示中にエラーが起きました。")

@bot.tree.command(name="bump_time", description="次のBumpリマインド時刻を表示します。")
async def bump_time(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        reminder = await db.get_reminder()
        if reminder:
            remind_at = reminder['remind_at']
            await interaction.followup.send(f"次のBumpが可能になるのは <t:{int(remind_at.timestamp())}:R> です。")
        else:
            await interaction.followup.send("現在、リマインドは設定されていません。`/bump` をお願いします！")
    except Exception as e:
        logging.error(f"Error in /bump_time: {e}", exc_info=True)
        await interaction.followup.send("ごめん！リマインド時刻の表示中にエラーが起きました。")

# --- ★★★ここからが新しいコード★★★ ---
# --- 管理者用コマンド ---
@bot.tree.command(name="scan_history", description="【管理者用】過去のBump履歴をスキャンして登録します。")
@app_commands.checks.has_permissions(administrator=True) # 管理者だけが使えるように制限
async def scan_history(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10000] = 1000):
    # ephemeral=True で、コマンドの実行者だけにメッセージが見えるようにする
    await interaction.response.defer(ephemeral=True, thinking=True)
    
    logging.info(f"User {interaction.user.name} started history scan for {limit} messages.")
    
    target_channel = interaction.channel
    found_bumps = 0
    processed_users = {}

    async for message in target_channel.history(limit=limit):
        if message.author.id == DISBOARD_BOT_ID and message.embeds:
            embed = message.embeds[0]
            if embed.description and "表示順をアップしたよ" in embed.description:
                match = re.search(r'<@!?(\d+)>', embed.description)
                if match:
                    user_id = int(match.group(1))
                    if user_id in processed_users:
                        processed_users[user_id] += 1
                    else:
                        processed_users[user_id] = 1
                    found_bumps += 1

    if not processed_users:
        await interaction.followup.send(f"{limit}件のメッセージをスキャンしましたが、Bump履歴は見つかりませんでした。", ephemeral=True)
        return

    # データベースに記録
    for user_id, count in processed_users.items():
        for _ in range(count):
            await db.record_bump(user_id)
            
    logging.info(f"Scan complete. Found {found_bumps} bumps. Updating database.")

    user_list_str = []
    for user_id, count in sorted(processed_users.items(), key=lambda item: item[1], reverse=True):
        try:
            user = await bot.fetch_user(user_id)
            user_list_str.append(f"・{user.display_name}: {count}回")
        except discord.NotFound:
            user_list_str.append(f"・不明なユーザー(ID:{user_id}): {count}回")

    result_message = (
        f"過去ログのスキャンが完了しました！\n"
        f"**{found_bumps}件**のBumpを検出し、データベースに登録しました。\n\n"
        f"【検出結果】\n"
        f"{'\n'.join(user_list_str)}\n\n"
        f"**【超重要】このコマンドは、同じ履歴を何度も登録してしまうので、サーバーのセットアップ時に一度だけ使用してください！**"
    )

    await interaction.followup.send(result_message, ephemeral=True)

# scan_historyコマンドでエラーが起きた時の処理
@scan_history.error
async def on_scan_history_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("このコマンドはサーバーの管理者しか使えません。", ephemeral=True)
    else:
        logging.error(f"Error in /scan_history: {error}", exc_info=True)
        await interaction.response.send_message(f"スキャン中にエラーが発生しました。\n`{error}`", ephemeral=True)

# --- ★★★新しいコードはここまで★★★ ---

# --- 定期タスク ---
@tasks.loop(minutes=1)
async def reminder_task():
    try:
        reminder = await db.get_reminder()
        if reminder and datetime.datetime.now(datetime.timezone.utc) >= reminder['remind_at']:
            channel = bot.get_channel(reminder['channel_id']) or await bot.fetch_channel(reminder['channel_id'])
            if channel:
                await channel.send("⏰ そろそろBumpの時間だよ！`/bump` をお願いします！")
            await db.clear_reminder()
            logging.info("Reminder message sent.")
    except Exception as e:
        logging.error(f"Error in reminder task: {e}", exc_info=True)

# --- 起動処理 ---
def main():
    web_thread = threading.Thread(target=run_web_server)
    web_thread.start()
    if TOKEN and DATABASE_URL:
        logging.info("Token and Database URL found. Starting bot...")
        bot.run(TOKEN)
    else:
        logging.error("!!! FATAL: DISCORD_BOT_TOKEN or DATABASE_URL not found in environment variables.")

if __name__ == "__main__":
    main()
