import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, re, random, datetime, asyncio, threading, logging
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
def index(): return "BUMPくん Ver4.0 is running!", 200
@app.route('/health')
def health_check(): return "OK", 200
def run_web_server(): app.run(host='0.0.0.0', port=os.environ.get('PORT', 10000))


# --- Botのイベント処理 ---

@bot.event
async def on_ready():
    logging.info("Bot is preparing...")
    try:
        await db.init_db()
        logging.info("Database initialized.")
        if not reminder_task.is_running():
            reminder_task.start()
            logging.info("Reminder task started.")
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
            # まずは通常通りBumpを1回記録
            count = await db.record_bump(user.id)
            
            # ★★★★★★★ Ver4.0 シンプルスロットマシン機能 ★★★★★★★
            
            # スロットの絵柄を準備 (候補3)
            reels = ['💎', '⭐', '🔔', '😭']
            slot_result = [random.choice(reels) for _ in range(3)]
            
            # スロットの回転を演出
            slot_machine_msg = await message.channel.send(f"{user.mention} さんの運試しスロット！\n`[ ? | ? | ? ]`")
            await asyncio.sleep(1)
            await slot_machine_msg.edit(content=f"{user.mention} さんの運試しスロット！\n`[ {slot_result[0]} | ? | ? ]`")
            await asyncio.sleep(1)
            await slot_machine_msg.edit(content=f"{user.mention} さんの運試しスロット！\n`[ {slot_result[0]} | {slot_result[1]} | ? ]`")
            await asyncio.sleep(1)
            await slot_machine_msg.edit(content=f"{user.mention} さんの運試しスロット！\n`[ {slot_result[0]} | {slot_result[1]} | {slot_result[2]} ]`")
            
            # 当たり判定と景品処理
            bonus_points = 0
            result_message = ""

            if slot_result.count('💎') == 3:
                bonus_points = 10
                result_message = f"🎉🎉🎉 **JACKPOT!!** 🎉🎉🎉\nなんと奇跡の **ダイヤモンド揃い**！\nボーナスとしてBump回数を **+{bonus_points}回** プレゼント！"
            elif slot_result.count('⭐') == 3:
                bonus_points = 3
                result_message = f"🎊🎊 **BIG WIN!** 🎊🎊\n見事な **スター揃い**！\nボーナス **+{bonus_points}回** ゲットだ！"
            elif slot_result.count('🔔') == 3:
                bonus_points = 1
                result_message = f"🔔 **WIN!** 🔔\nラッキーな **ベル揃い**！\nささやかなボーナス **+{bonus_points}回** をどうぞ！"
            elif slot_result[0] == slot_result[1] or slot_result[1] == slot_result[2] or slot_result[0] == slot_result[2]:
                 result_message = "おしい！あと一歩だったね！"
            else:
                result_message = "残念！次のBumpでリベンジだ！"
            
            # スロットの結果を送信
            await message.channel.send(result_message)

            # ボーナスポイントをデータベースに記録
            if bonus_points > 0:
                # bonus_points分、record_bumpを呼び出す
                for _ in range(bonus_points):
                    count = await db.record_bump(user.id)
                await message.channel.send(f"君の累計Bump回数は **{count}回** になったよ！")

            # ★★★★★★★ スロットマシンここまで ★★★★★★★

            # 最後に、Ver3の称号付き感謝メッセージを表示する
            await asyncio.sleep(2) # スロットの結果から少し間をあける
            
            next_bump_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
            
            bump_title = "BUMPの新人🔰"
            if 10 <= count < 50: bump_title = "BUMPの常連⭐"
            elif 50 <= count < 100: bump_title = "BUMPの達人✨"
            elif 100 <= count < 200: bump_title = "BUMPの英雄👑"
            elif count >= 200: bump_title = "BUMPの神様⛩️"

            thanks_messages = [
                "最高のBumpをありがとう！君はサーバーの希望だ！",
                "ナイスBump！この調子でサーバーを盛り上げていこう！",
                "君のBumpが、サーバーを次のステージへ押し上げる！サンキュー！",
                "お疲れ様！君の貢献に心から感謝するよ！"
            ]
            
            response_message = (
                f"**{bump_title}** {user.mention}\n"
                f"{random.choice(thanks_messages)}\n\n"
                f"現在の累計Bump回数は **{count}回** です！\n"
                f"次のBumpは <t:{int(next_bump_time.timestamp())}:R> に可能になります。またよろしくね！"
            )

            await message.channel.send(response_message)
            
            # 記念回数のお祝い
            # ボーナスで記念回数をまたぐ可能性があるので、ここで判定
            if count - bonus_points < 50 <= count: await message.channel.send(f"🎉🎉Congratulation!!🎉🎉 {user.mention} ついに累計 **50回** のBumpを達成！{bump_title}になった！")
            if count - bonus_points < 100 <= count: await message.channel.send(f"🎉🎉Congratulation!!🎉🎉 {user.mention} ついに累計 **100回** のBumpを達成！{bump_title}になった！")
            # ... 他の記念回数も同様に設定可能

            # リマインダー設定
            await db.set_reminder(message.channel.id, next_bump_time)
            logging.info(f"Reminder set for {next_bump_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        except Exception as e:
            logging.error(f"Error processing bump after detection: {e}", exc_info=True)
            await message.channel.send("Bumpは検知できたけど、記録中にエラーが起きたみたい…ごめんね！")


# --- スラッシュコマンド (Ver3.0から変更なし) ---

@bot.tree.command(name="bump_top", description="サーバーを盛り上げる英雄たちのランキングを表示します。")
async def bump_top(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        top_users = await db.get_top_users()
        server_total_bumps = await db.get_total_bumps()

        if not top_users:
            await interaction.followup.send("まだ誰もBumpしていません。君が最初のヒーローになろう！")
            return

        embed = discord.Embed(
            title="🏆 BUMPランキングボード 🏆",
            description=f"サーバー合計Bump: **{server_total_bumps}** 回！みんな、本当にありがとう！",
            color=discord.Color.gold()
        )

        for i, record in enumerate(top_users):
            user = await bot.fetch_user(record['user_id'])
            user_bumps = record['bump_count']
            
            rank_emoji = ""
            if i == 0: rank_emoji = "🥇"
            elif i == 1: rank_emoji = "🥈"
            elif i == 2: rank_emoji = "🥉"
            else: rank_emoji = f"**{i+1}位**"
            
            gap_text = ""
            if i > 0:
                prev_user_bumps = top_users[i-1]['bump_count']
                gap = prev_user_bumps - user_bumps
                if gap > 0:
                    gap_text = f" (あと{gap}回でランクアップ！)"

            embed.add_field(
                name=f"{rank_emoji} {user.display_name}",
                value=f"> **{user_bumps}** 回" + gap_text,
                inline=False
            )
            
        embed.set_footer(text="君のBumpが、このサーバーの歴史を創る！")
        await interaction.followup.send(embed=embed)

    except Exception as e:
        logging.error(f"Error in /bump_top: {e}", exc_info=True)
        await interaction.followup.send("ごめん！ランキングの表示中にエラーが起きました。")


@bot.tree.command(name="bump_user", description="指定したユーザーのBump回数を表示します。")
# ... (このコマンドは変更がないので、コードは省略)
async def bump_user(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer()
    try:
        count = await db.get_user_count(user.id)
        await interaction.followup.send(f"{user.display_name}さんの累計Bump回数は **{count}回** です。")
    except Exception as e:
        logging.error(f"Error in /bump_user: {e}", exc_info=True)
        await interaction.followup.send("ごめん！回数の表示中にエラーが起きました。")

@bot.tree.command(name="bump_time", description="次のBumpリマインド時刻を表示します。")
# ... (このコマンドは変更がないので、コードは省略)
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
# ... (このコマンドは変更がないので、コードは省略)
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
# ... (このエラー処理は変更がないので、コードは省略)
async def on_scan_history_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("このコマンドはサーバーの管理者しか使えません。", ephemeral=True)
    else:
        await interaction.response.send_message(f"スキャン中にエラー: `{error}`", ephemeral=True)


# --- 定期タスク (変更なし) ---
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


# --- 起動処理 (変更なし) ---
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
