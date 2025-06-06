import discord
from discord.ext import commands, tasks
import os
import re
import random
import datetime
import asyncio
import database as db # さっき作ったdatabase.pyを読み込む
from flask import Flask
import threading

# --- 設定項目 ---
# Discord Botのトークン（あとでRenderで設定する）
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
# DisboardのBotのID
DISBOARD_BOT_ID = 302050872383242240

# --- ここからBotのプログラム ---

# Botに必要な権限（Intent）を設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

# Botのインスタンスを作成
bot = commands.Bot(command_prefix='/', intents=intents)

# 起動したときに実行される処理
@bot.event
async def on_ready():
    print(f'{bot.user.name} が起動しました！')
    # データベースの初期化
    await db.init_db()
    # リマインダータスクを開始
    reminder_task.start()
    # スラッシュコマンドを同期
    await bot.tree.sync()

# メッセージを受信したときに実行される処理
@bot.event
async def on_message(message):
    # メッセージの送信者がDisboardのBotか、埋め込みメッセージがあるかを確認
    if message.author.id == DISBOARD_BOT_ID and message.embeds:
        embed = message.embeds[0]
        # Bump成功メッセージかどうかを判定
        if "表示順をアップしたよ" in embed.description:
            print("Bump成功メッセージを検知しました。")
            
            # Bumpしたユーザーを特定する（正規表現という方法で名前を探す）
            match = re.search(r'<@!?(\d+)>', embed.description)
            if match:
                user_id = int(match.group(1))
                user = bot.get_user(user_id)
                
                # データベースにBump回数を記録
                count = await db.record_bump(user_id)
                
                # 感謝のメッセージを送信
                thanks_messages = [
                    f"ありがとう！サーバーが盛り上がるね！",
                    f"ナイスBump！君はヒーローだ！",
                    f"サンキュー！次も頼んだよ！",
                    f"お疲れ様！ゆっくり休んでね！"
                ]
                await message.channel.send(f"{user.mention} {random.choice(thanks_messages)} (累計 {count} 回)")

                # 記念回数のお祝い
                if count in [10, 50, 100, 150, 200]:
                     await message.channel.send(f"🎉🎉Congratulation!!🎉🎉 {user.mention} なんと累計 **{count}回** のBumpを達成しました！本当にありがとう！")

                # 2時間後のリマインダーを設定
                remind_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
                await db.set_reminder(message.channel.id, remind_time)
                print(f"次のリマインドを {remind_time.strftime('%Y-%m-%d %H:%M:%S')} に設定しました。")


# --- スラッシュコマンドの定義 ---

# Bumpランキングを表示するコマンド
@bot.tree.command(name="bump_top", description="Bump回数のトップ5ランキングを表示します。")
async def bump_top(interaction: discord.Interaction):
    await interaction.response.defer() # 応答を少し待つ
    top_users = await db.get_top_users()
    
    if not top_users:
        await interaction.followup.send("まだ誰もBumpしていません。")
        return

    embed = discord.Embed(title="🏆 Bumpランキング 🏆", color=discord.Color.gold())
    
    for i, record in enumerate(top_users):
        try:
            user = await bot.fetch_user(record['user_id'])
            username = user.display_name
        except discord.NotFound:
            username = f"ID: {record['user_id']}"
        
        embed.add_field(name=f"{i+1}位: {username}", value=f"{record['bump_count']} 回", inline=False)
        
    await interaction.followup.send(embed=embed)


# 指定したユーザーのBump回数を表示するコマンド
@bot.tree.command(name="bump_user", description="指定したユーザーのBump回数を表示します。")
async def bump_user(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer()
    count = await db.get_user_count(user.id)
    await interaction.followup.send(f"{user.display_name}さんの累計Bump回数は **{count}回** です。")

# 次のBump可能時刻を表示するコマンド
@bot.tree.command(name="bump_time", description="次のBumpリマインド時刻を表示します。")
async def bump_time(interaction: discord.Interaction):
    await interaction.response.defer()
    reminder = await db.get_reminder()
    if reminder:
        remind_at = reminder['remind_at']
        # Discordのタイムスタンプ形式 <t:UNIXタイムスタンプ:R> を使うと、見る人の環境に合わせて表示される
        await interaction.followup.send(f"次のBumpが可能になるのは <t:{int(remind_at.timestamp())}:R> です。")
    else:
        await interaction.followup.send("現在、リマインドは設定されていません。`/bump` をお願いします！")


# --- 定期的に実行するタスク ---

# 1分ごとにリマインダーをチェックするタスク
@tasks.loop(minutes=1)
async def reminder_task():
    reminder = await db.get_reminder()
    if reminder:
        now = datetime.datetime.now(datetime.timezone.utc)
        if now >= reminder['remind_at']:
            channel = bot.get_channel(reminder['channel_id'])
            if channel:
                # お知らせ用のロールなどがあれば、ここでメンションできる
                # role = discord.utils.get(channel.guild.roles, name="BUMP通知")
                # if role:
                #    await channel.send(f"{role.mention} そろそろBumpの時間だよ！`/bump` をお願いします！")
                # else:
                await channel.send("⏰ そろそろBumpの時間だよ！`/bump` をお願いします！")
            
            await db.clear_reminder()
            print("リマインドメッセージを送信し、設定を削除しました。")

# --- Renderのスリープを防ぐためのWebサーバー機能 ---
# これはおまじないだと思ってOK！
app = Flask(__name__)

@app.route('/health')
def health_check():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# --- BotとWebサーバーを同時に動かす ---
if __name__ == '__main__':
    # Webサーバーを別のスレッドで起動
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Discord Botを起動
    bot.run(TOKEN)