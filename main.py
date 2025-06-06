import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, re, random, datetime, asyncio, threading, logging
import database as db
from flask import Flask

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
DISBOARD_BOT_ID = 302050872383242240
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix='/', intents=intents)
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is running!", 200
@app.route('/health')
def health_check(): return "OK", 200
def run_web_server(): app.run(host='0.0.0.0', port=os.environ.get('PORT', 10000))

@bot.event
async def on_ready():
    logging.info("Bot is preparing...")
    try:
        logging.info("Connecting to database...")
        pool = await db.get_pool()
        async with pool.acquire(): logging.info("Database connection successful.")
        await pool.close()
        logging.info("Initializing database table...")
        await db.init_db()
        logging.info("Database table initialized.")
        if not reminder_task.is_running():
            reminder_task.start()
            logging.info("Reminder task started.")
        await bot.tree.sync()
        logging.info("Slash commands synchronized.")
        logging.info(f"------\nBot started successfully: {bot.user.name}\n------")
    except Exception as e:
        logging.error(f"!!! CRITICAL ERROR ON STARTUP: {e}", exc_info=True)

# ★★★★★★★ ここが最終進化を遂げた部分 ★★★★★★★
@bot.event
async def on_message(message):
    # メッセージの送信者がDisboardのBotで、かつ、そのメッセージに「電子指紋」(interaction)が残っているか？
    if message.author.id == DISBOARD_BOT_ID and message.interaction is not None:
        
        # 指紋の名前が 'bump' コマンドのものか？
        if message.interaction.name == 'bump':
            
            # 指紋から、コマンドを実行したユーザー（犯人）を特定！
            user = message.interaction.user
            
            logging.info(f"SUCCESS! Bump interaction detected by user: {user.name} ({user.id})")

            try:
                # データベースに記録し、お礼を言う
                count = await db.record_bump(user.id)
                
                thanks_messages = ["ありがとう！サーバーが盛り上がるね！", "ナイスBump！君はヒーローだ！", "サンキュー！次も頼んだよ！", "お疲れ様！ゆっくり休んでね！"]
                await message.channel.send(f"{user.mention} {random.choice(thanks_messages)} (累計 **{count}** 回)")

                if count in [10, 50, 100, 150, 200]:
                     await message.channel.send(f"🎉🎉Congratulation!!🎉🎉 {user.mention} なんと累計 **{count}回** のBumpを達成しました！本当にありがとう！")

                remind_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
                await db.set_reminder(message.channel.id, remind_time)
                logging.info(f"Reminder set for {remind_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            except Exception as e:
                logging.error(f"Error processing bump after detection: {e}", exc_info=True)
                await message.channel.send("Bumpは検知できたけど、記録中にエラーが起きたみたい…ごめんね！")
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

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

@bot.tree.command(name="scan_history", description="【管理者用/一度きり】過去のBump履歴をスキャンして登録します。")
@app_commands.checks.has_permissions(administrator=True)
async def scan_history(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 10000] = 1000):
    await interaction.response.defer(ephemeral=True, thinking=True)
    if await db.is_scan_completed():
        await interaction.followup.send(
            "**エラー：過去ログのスキャンは既に完了しています！**\nこのコマンドは、安全のため一度しか実行できません。",
            ephemeral=True
        )
        return
    logging.info(f"User {interaction.user.name} started history scan.")
    target_channel, found_bumps, processed_users = interaction.channel, 0, {}
    # スキャン部分は、新しい仕様ではユーザーを特定できないので、現状では不正確になる可能性がある。
    # しかし、今後のBumpは正確に記録されるため、コマンド自体は残しておく。
    async for message in target_channel.history(limit=limit):
        if message.author.id == DISBOARD_BOT_ID and message.interaction and message.interaction.name == 'bump':
            user_id = message.interaction.user.id
            processed_users[user_id] = processed_users.get(user_id, 0) + 1
            found_bumps += 1
    if not processed_users:
        await interaction.followup.send(f"{limit}件のメッセージをスキャンしましたが、Bump履歴は見つかりませんでした。", ephemeral=True)
        return
    for user_id, count in processed_users.items():
        # 注意：この方法では、誰が何回Bumpしたかを正確に記録するのではなく、
        # 見つかったBumpの回数分だけ、それぞれのユーザーのカウントを増やす形になる。
        # より正確にするには、データベースの構造から見直す必要があるため、今回は簡易的な実装とする。
        current_count = await db.get_user_count(user_id)
        for _ in range(count):
            current_count += 1
            # 1回ずつ記録するのではなく、まとめて更新する方が効率的だが、既存の関数を流用する
            await db.record_bump(user_id) # この関数は1増やすだけなので、複数回呼び出す
            
    await db.mark_scan_as_completed()
    logging.info("Marked history scan as completed.")
    user_list_text = "\n".join([f"・<@{uid}>: {c}回" for uid, c in processed_users.items()])
    result_message = (f"過去ログのスキャンが完了しました！\n**{found_bumps}件**のBumpを検出しました。\n\n【注意】\n現在のDisboardの仕様上、過去ログからの正確な回数反映は困難です。このスキャンは参考程度のものです。今後のBumpから正確に記録されます。\n\n**安全装置が作動しました。今後このコマンドは実行できません。**")
    await interaction.followup.send(result_message, ephemeral=True)

@scan_history.error
async def on_scan_history_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("このコマンドはサーバーの管理者しか使えません。", ephemeral=True)
    else:
        logging.error(f"Error in /scan_history: {error}", exc_info=True)
        await interaction.response.send_message(f"スキャン中にエラーが発生しました。\n`{error}`", ephemeral=True)

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

def main():
    web_thread = threading.Thread(target=run_web_server)
    web_thread.start()
    if TOKEN and DATABASE_URL:
        bot.run(TOKEN)
    else:
        logging.error("!!! FATAL: DISCORD_BOT_TOKEN or DATABASE_URL not found.")

if __name__ == "__main__":
    main()
