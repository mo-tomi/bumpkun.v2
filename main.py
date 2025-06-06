import discord
from discord.ext import commands, tasks
import os
import re
import random
import datetime
import asyncio
import database as db
from flask import Flask
import threading

# --- 設定 ---
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
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
def hello_world():
    return 'BUMPくんは元気に稼働中！'

def run_web_server():
    app.run(host='0.0.0.0', port=10000)

# --- Botのイベント ---
@bot.event
async def on_ready():
    await db.init_db()
    if not reminder_task.is_running():
        reminder_task.start()
    await bot.tree.sync()
    print('------')
    print(f'Bot起動成功: {bot.user.name}')
    print('------')

@bot.event
async def on_message(message):
    if message.author.id == DISBOARD_BOT_ID and message.embeds:
        embed = message.embeds[0]
        if embed.description and "表示順をアップしたよ" in embed.description:
            print("Bump成功メッセージを検知。")
            match = re.search(r'<@!?(\d+)>', embed.description)
            if match:
                user_id = int(match.group(1))
                user = bot.get_user(user_id) or await bot.fetch_user(user_id)
                if not user:
                    print(f"ユーザーID取得失敗: {user_id}")
                    return
                
                count = await db.record_bump(user_id)
                print(f"記録: {user.name} ({user_id}), 累計{count}回")
                
                thanks_messages = [
                    "ありがとう！サーバーが盛り上がるね！",
                    "ナイスBump！君はヒーローだ！",
                    "サンキュー！次も頼んだよ！",
                    "お疲れ様！ゆっくり休んでね！"
                ]
                await message.channel.send(f"{user.mention} {random.choice(thanks_messages)} (累計 **{count}** 回)")

                if count in [10, 50, 100, 150, 200]:
                     await message.channel.send(f"🎉🎉Congratulation!!🎉🎉 {user.mention} なんと累計 **{count}回** のBumpを達成しました！本当にありがとう！")

                remind_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
                await db.set_reminder(message.channel.id, remind_time)
                print(f"リマインダー設定: {remind_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

# --- スラッシュコマンド ---
# (中身は同じなので省略)
@bot.tree.command(name="bump_top", description="Bump回数のトップ5ランキングを表示します。")
async def bump_top(interaction: discord.Interaction):
    await interaction.response.defer()
    top_users = await db.get_top_users()
    if not top_users:
        await interaction.followup.send("まだ誰もBumpしていません。まずは`/bump`してみよう！")
        return
    embed = discord.Embed(title="🏆 Bumpランキング 🏆", color=discord.Color.gold())
    rank_text = ""
    for i, record in enumerate(top_users):
        try:
            user = await bot.fetch_user(record['user_id'])
            username = user.display_name
        except discord.NotFound:
            username = f"不明なユーザー (ID: {record['user_id']})"
        rank_text += f"**{i+1}位**: {username} - **{record['bump_count']}** 回\n"
    embed.description = rank_text
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="bump_user", description="指定したユーザーのBump回数を表示します。")
async def bump_user(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer()
    count = await db.get_user_count(user.id)
    await interaction.followup.send(f"{user.display_name}さんの累計Bump回数は **{count}回** です。")

@bot.tree.command(name="bump_time", description="次のBumpリマインド時刻を表示します。")
async def bump_time(interaction: discord.Interaction):
    await interaction.response.defer()
    reminder = await db.get_reminder()
    if reminder:
        remind_at = reminder['remind_at']
        await interaction.followup.send(f"次のBumpが可能になるのは <t:{int(remind_at.timestamp())}:R> です。")
    else:
        await interaction.followup.send("現在、リマインドは設定されていません。`/bump` をお願いします！")

# --- 定期タスク ---
@tasks.loop(minutes=1)
async def reminder_task():
    reminder = await db.get_reminder()
    if reminder and datetime.datetime.now(datetime.timezone.utc) >= reminder['remind_at']:
        try:
            channel = bot.get_channel(reminder['channel_id']) or await bot.fetch_channel(reminder['channel_id'])
            if channel:
                await channel.send("⏰ そろそろBumpの時間だよ！`/bump` をお願いします！")
            await db.clear_reminder()
            print("リマインドメッセージを送信しました。")
        except Exception as e:
            print(f"リマインダータスクでエラー: {e}")

# --- 起動処理 ---
# 1. Webサーバーを別のスレッドで起動
web_thread = threading.Thread(target=run_web_server)
web_thread.start()

# 2. Botを起動
bot.run(TOKEN)
