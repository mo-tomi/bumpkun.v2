# 2回目のデプロイに使う main.py (これが完成版！)
import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import re
import random
import datetime
import asyncio
import threading
import logging
import database as db
from flask import Flask

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO)
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
def index(): return "BUMPくん (Advanced Reminder Version) is running!", 200
@app.route('/health')
def health_check(): return "OK", 200
def run_web_server(): app.run(host='0.0.0.0', port=os.environ.get('PORT', 10000))


# --- Botのイベント処理 ---

@bot.event
async def on_ready():
    logging.info("Bot is preparing...")
    try:
        # 呪文はもういらない！きれいな状態に戻す
        await db.init_db()
        logging.info("Database initialized.")
        if not reminder_task.is_running():
            reminder_task.start()
            logging.info("Advanced Reminder task started.")
        await bot.tree.sync()
        logging.info("Slash commands synchronized.")
        logging.info(f"------\nBot started successfully: {bot.user.name}\n------")
    except Exception as e:
        logging.error(f"!!! CRITICAL ERROR ON STARTUP: {e}", exc_info=True)


@bot.event
async def on_message(message):
    if message.author.id == DISBOARD_BOT_ID and message.interaction is not None and message.interaction.name == 'bump':
        user = message.interaction.user
        logging.info(f"SUCCESS! Bump interaction detected by user: {user.name} ({user.id})")
        
        try:
            count = await db.record_bump(user.id)
            
            reels = ['💎', '⭐', '🔔', '😭']
            slot_result = [random.choice(reels) for _ in range(3)]
            slot_machine_msg = await message.channel.send(f"{user.mention} さんの運試しスロット！\n`[ ? | ? | ? ]`")
            await asyncio.sleep(1); await slot_machine_msg.edit(content=f"{user.mention} さんの運試しスロット！\n`[ {slot_result[0]} | ? | ? ]`")
            await asyncio.sleep(1); await slot_machine_msg.edit(content=f"{user.mention} さんの運試しスロット！\n`[ {slot_result[0]} | {slot_result[1]} | ? ]`")
            await asyncio.sleep(1); await slot_machine_msg.edit(content=f"{user.mention} さんの運試しスロット！\n`[ {slot_result[0]} | {slot_result[1]} | {slot_result[2]} ]`")
            result_message = ""
            if slot_result.count('💎') == 3: result_message = "🎉🎉🎉 **JACKPOT!!** 🎉🎉🎉\nなんと奇跡の **ダイヤモンド揃い**！すごい強運の持ち主だ！"
            elif slot_result.count('⭐') == 3: result_message = "🎊🎊 **BIG WIN!** 🎊🎊\n見事な **スター揃い**！今日は良いことがありそう！"
            elif slot_result.count('🔔') == 3: result_message = "🔔 **WIN!** 🔔\nラッキーな **ベル揃い**！ささやかな幸せ！"
            elif slot_result[0] == slot_result[1] or slot_result[1] == slot_result[2] or slot_result[0] == slot_result[2]: result_message = "おしい！あと一歩だったね！"
            else: result_message = "残念！次のBumpでリベンジだ！"
            await message.channel.send(result_message)
            await asyncio.sleep(2)
            next_bump_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
            bump_title = "BUMPの新人🔰"
            if 10 <= count < 50: bump_title = "BUMPの常連⭐"
            elif 50 <= count < 100: bump_title = "BUMPの達人✨"
            elif 100 <= count < 200: bump_title = "BUMPの英雄👑"
            elif count >= 200: bump_title = "BUMPの神様⛩️"
            thanks_messages = ["最高のBumpをありがとう！君はサーバーの希望だ！", "ナイスBump！この調子でサーバーを盛り上げていこう！", "君のBumpが、サーバーを次のステージへ押し上げる！サンキュー！", "お疲れ様！君の貢献に心から感謝するよ！"]
            response_message = (f"**{bump_title}** {user.mention}\n{random.choice(thanks_messages)}\n\nあなたの累計Bump回数は **{count}回** です！\n次のBumpは <t:{int(next_bump_time.timestamp())}:R> に可能になります。またよろしくね！")
            await message.channel.send(response_message)
            if count in [10, 50, 100, 150, 200]: await message.channel.send(f"🎉🎉Congratulation!!🎉🎉 {user.mention} ついに累計 **{count}回** のBumpを達成！{bump_title}になった！")

            await db.set_reminder(message.channel.id, next_bump_time)
            logging.info(f"Reminder set for {next_bump_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        except Exception as e:
            logging.error(f"Error processing bump after detection: {e}", exc_info=True)
            await message.channel.send("Bumpは検知できたけど、記録中にエラーが起きたみたい…ごめんね！")


# --- スラッシュコマンド ---
@bot.tree.command(name="bump_top", description="サーバーを盛り上げる英雄たちのランキングを表示します。")
async def bump_top(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        top_users = await db.get_top_users()
        server_total_bumps = await db.get_total_bumps()
        if not top_users:
            await interaction.followup.send("まだ誰もBumpしていません。君が最初のヒーローになろう！")
            return
        embed = discord.Embed(title="🏆 BUMPランキングボード 🏆", description=f"サーバー合計Bump: **{server_total_bumps}** 回！みんな、本当にありがとう！", color=discord.Color.gold())
        for i, record in enumerate(top_users):
            user = await bot.fetch_user(record['user_id'])
            user_bumps = record['bump_count']
            rank_emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"**{i+1}位**"
            embed.add_field(name=f"{rank_emoji} {user.display_name}", value=f"> **{user_bumps}** 回", inline=False)
        embed.set_footer(text="君のBumpが、このサーバーの歴史を創る！")
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
        await interaction.followup.send("**エラー：過去ログのスキャンは既に完了しています！**", ephemeral=True)
        return
    found_bumps = 0
    async for message in interaction.channel.history(limit=limit):
        if message.author.id == DISBOARD_BOT_ID and message.interaction and message.interaction.name == 'bump':
            await db.record_bump(message.interaction.user.id)
            found_bumps += 1
    if found_bumps == 0:
        await interaction.followup.send(f"{limit}件のメッセージをスキャンしましたが、Bump履歴は見つかりませんでした。", ephemeral=True)
        return
    await db.mark_scan_as_completed()
    await interaction.followup.send(f"スキャン完了！**{found_bumps}件**のBumpを記録しました。\n**安全装置が作動しました。**", ephemeral=True)

@scan_history.error
async def on_scan_history_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("このコマンドはサーバーの管理者しか使えません。", ephemeral=True)
    else:
        await interaction.response.send_message(f"スキャン中にエラー: `{error}`", ephemeral=True)

# --- 定期タスク (新しい2段階リマインダーロジック) ---
@tasks.loop(minutes=1)
async def reminder_task():
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
                channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
                if channel:
                    await channel.send("⏰ そろそろBumpの時間だよ！`/bump` をお願いします！")
                    logging.info(f"Sent 1st reminder to channel {channel_id}")
                    await db.update_reminder_status(channel_id, 'notified_1st') 
            except Exception as e:
                logging.error(f"Failed to send 1st reminder: {e}")

        elif status == 'notified_1st' and now_utc >= (remind_at + datetime.timedelta(minutes=30)):
            try:
                channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
                if channel:
                    top_users_records = await db.get_top_users(limit=5)
                    if top_users_records:
                        mentions = []
                        for record in top_users_records:
                            try:
                                user = channel.guild.get_member(record['user_id']) or await bot.fetch_user(record['user_id'])
                                mentions.append(user.mention)
                            except discord.NotFound:
                                logging.warning(f"Could not find user with ID {record['user_id']}")
                        
                        if mentions:
                            mentions_str = " ".join(mentions)
                            message = (
                                f"{mentions_str}\n"
                                "皆様、いつもサーバーを盛り上げてくださり、本当にありがとうございます。\n"
                                "もしもお時間よろしければ、Bumpにご協力いただけませんでしょうか…？🙇"
                            )
                            await channel.send(message)
                            logging.info(f"Sent 2nd (humble) reminder to channel {channel_id}")
                    
                    await db.clear_reminder()
            except Exception as e:
                logging.error(f"Failed to send 2nd reminder: {e}")

    except Exception as e:
        logging.error(f"Error in reminder task: {e}", exc_info=True)


# --- 起動処理 ---
def main():
    web_thread = threading.Thread(target=run_web_server)
    web_thread.start()
    if TOKEN:
        try:
            bot.run(TOKEN)
        except Exception as e:
            logging.error(f"!!! FATAL: Bot failed to run: {e}", exc_info=True)
    else:
        logging.error("!!! FATAL: DISCORD_BOT_TOKEN not found.")

if __name__ == "__main__":
    main()
