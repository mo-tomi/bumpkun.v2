@bot.event
async def on_message(message):
    if message.author.id == DISBOARD_BOT_ID and message.embeds:
        embed = message.embeds[0]
        
        # --- ここからが探偵コード ---
        logging.info("--- DISBOARD MESSAGE DETECTED ---")
        logging.info(f"Embed Title: {embed.title}")
        logging.info(f"Embed Description: {embed.description}")
        logging.info(f"Embed Fields: {embed.fields}")
        logging.info(f"Embed Footer: {embed.footer}")
        logging.info(f"Embed Author: {embed.author}")
        # --- ここまでが探偵コード ---

        if embed.description and "表示順をアップしたよ" in embed.description:
            logging.info("Bump success text found in description.")
            
            # ユーザーIDを探す
            user_id = None
            
            # パターン1: 説明文から探す
            match_desc = re.search(r'<@!?(\d+)>', embed.description)
            if match_desc:
                user_id = int(match_desc.group(1))
                logging.info(f"User found in description: {user_id}")
            
            # もし見つからなかったら、他の場所も探す（将来の仕様変更のため）
            # (今はまだ何もしない)
            
            if user_id:
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
            else:
                # 犯人が見つからなかった場合のログ
                logging.warning("!!! COULD NOT FIND USER MENTION IN THE BUMP MESSAGE !!!")
