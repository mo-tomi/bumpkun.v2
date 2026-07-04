# cogs/bump.py - Bump検知 + スロットマシン演出(2種類からランダム選択)

import discord
from discord.ext import commands
import random
import datetime
import asyncio
import logging
import database as db
from config import (
    DISBOARD_BOT_ID, BUMP_COOLDOWN_HOURS,
    SLOT_MACHINES,
    THANKS_MESSAGES, MILESTONES,
    get_bump_title, get_streak_badge,
)


def _detect_bump(message: discord.Message):
    """DISBOARDのBumpを検知してユーザーを返す。検知できなければNone"""
    if message.author.id != DISBOARD_BOT_ID:
        return None

    user = None

    # interaction_metadata(新API)を優先チェック
    meta = getattr(message, 'interaction_metadata', None)
    if meta is not None:
        name = getattr(meta, 'name', None) or getattr(meta, 'command_name', None)
        if name == 'bump' or (name is None and hasattr(meta, 'user')):
            user = getattr(meta, 'user', None)

    # フォールバック: 旧 interaction
    if user is None:
        old = getattr(message, 'interaction', None)
        if old is not None and getattr(old, 'name', None) == 'bump':
            user = getattr(old, 'user', None)

    return user


class BumpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        user = _detect_bump(message)
        if user is None:
            return

        logging.info(f"Bump検知: {user.name} ({user.id})")

        try:
            result = await db.record_bump(user.id)
            count = result['bump_count']
            streak = result['current_streak']
            max_streak = result['max_streak']
            weekly = result['weekly_count']
            is_new_record = result['is_new_streak_record']

            # --- スロットマシン演出(2種類からランダムに選択) ---
            machine = random.choice(SLOT_MACHINES)
            machine_name = machine["name"]
            reels = machine["reels"]
            jackpot_messages = machine["jackpot_messages"]

            slot = [random.choice(reels) for _ in range(3)]
            msg = await message.channel.send(f"{user.name} さんの{machine_name}！\n`[ ? | ? | ? ]`")
            await asyncio.sleep(1)
            await msg.edit(content=f"{user.name} さんの{machine_name}！\n`[ {slot[0]} | ? | ? ]`")
            await asyncio.sleep(1)
            await msg.edit(content=f"{user.name} さんの{machine_name}！\n`[ {slot[0]} | {slot[1]} | ? ]`")
            await asyncio.sleep(1)
            await msg.edit(content=f"{user.name} さんの{machine_name}！\n`[ {slot[0]} | {slot[1]} | {slot[2]} ]`")

            # スロット結果判定
            if slot[0] == slot[1] == slot[2]:
                slot_msg = jackpot_messages.get(slot[0], "🎉 **揃った！** 🎉")
            elif slot[0] == slot[1] or slot[1] == slot[2] or slot[0] == slot[2]:
                slot_msg = "おしい！あと一歩だったね！"
            else:
                slot_msg = "残念！次のBumpでリベンジだ！"

            # --- Embed構築 ---
            title = get_bump_title(count)
            streak_badge = get_streak_badge(streak)
            next_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=BUMP_COOLDOWN_HOURS)

            embed = discord.Embed(
                title=f"{title}　{user.display_name}",
                description=slot_msg,
                color=discord.Color.gold() if slot[0] == slot[1] == slot[2] else discord.Color.blue(),
            )
            embed.set_thumbnail(url=user.display_avatar.url)

            # 統計フィールド
            stats_text = (
                f"累計: **{count}回**\n"
                f"今週: **{weekly}回**"
            )
            embed.add_field(name="📊 Bump記録", value=stats_text, inline=True)

            # Streak表示
            streak_text = f"連続: **{streak}日**"
            if streak_badge:
                streak_text += f"\n{streak_badge}"
            if max_streak > 1:
                streak_text += f"\n自己ベスト: **{max_streak}日**"
            embed.add_field(name="🔥 連続記録", value=streak_text, inline=True)

            # 次のBump時刻
            embed.add_field(
                name="⏰ 次のBump",
                value=f"<t:{int(next_time.timestamp())}:R>",
                inline=False,
            )

            # お礼メッセージ
            embed.set_footer(text=random.choice(THANKS_MESSAGES))

            await asyncio.sleep(2)
            await message.channel.send(embed=embed)

            # --- マイルストーン通知 ---
            if count in MILESTONES:
                milestone_embed = discord.Embed(
                    title="🎉🎉 Congratulation!! 🎉🎉",
                    description=(
                        f"{user.mention} ついに累計 **{count}回** のBumpを達成！\n"
                        f"**{title}** に昇格！"
                    ),
                    color=discord.Color.yellow(),
                )
                await message.channel.send(embed=milestone_embed)

            # --- 連続記録の自己ベスト更新通知 ---
            if is_new_record:
                await message.channel.send(
                    f"🔥 {user.mention} 連続Bump記録更新！ **{streak}日連続** おめでとう！"
                )

            # リマインダー設定
            await db.set_reminder(message.channel.id, next_time)
            logging.info(f"リマインダー設定: {next_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        except Exception as e:
            logging.error(f"Bump処理エラー: {e}", exc_info=True)
            await message.channel.send("Bumpは検知できたけど、記録中にエラーが起きたみたい…ごめんね！")


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpCog(bot))
