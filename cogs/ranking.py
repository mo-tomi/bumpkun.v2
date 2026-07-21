# cogs/ranking.py - ランキングコマンド（v3: 10位まで + 週間ランキング + 個人統計強化）

import discord
from discord.ext import commands
from discord import app_commands
import logging
import database as db
from config import RANKING_LIMIT, RANKING_EXCLUDED_NAMES, get_bump_title, get_streak_badge

# 退出者・除外対象を差し引いてもTOP{RANKING_LIMIT}を埋められるよう、候補を多めに取得する
RANKING_CANDIDATE_POOL = RANKING_LIMIT * 5 + len(RANKING_EXCLUDED_NAMES)


class RankingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _resolve_ranked_users(self, guild, records, limit):
        """レコードを解決し、サーバー在籍者だけをlimit件返す。

        fetch_userはグローバル検索のため、すでにサーバーを退出した人も
        引けてしまう。guildが分かる場合はfetch_memberで在籍を確認し、
        退出者・削除済みアカウントはランキングから除外する。
        """
        resolved = []
        for record in records:
            try:
                if guild is not None:
                    # サーバーに今も在籍している人だけを対象にする
                    user = await guild.fetch_member(record['user_id'])
                else:
                    user = await self.bot.fetch_user(record['user_id'])
                name = user.display_name
            except discord.NotFound:
                continue  # 退出済み or 存在しないアカウント → 除外
            except discord.HTTPException:
                continue  # 取得失敗時も安全側で除外

            if name in RANKING_EXCLUDED_NAMES or name.startswith("deleted_user_"):
                continue  # 削除済みアカウント(Discordのプレースホルダー名)を除外

            resolved.append((record, name))
            if len(resolved) >= limit:
                break

        return resolved

    @app_commands.command(name="bump_top", description="累計Bumpランキング（TOP10）を表示します。")
    async def bump_top(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            top_users = await db.get_top_users(RANKING_CANDIDATE_POOL)
            server_total = await db.get_total_bumps()

            ranked = await self._resolve_ranked_users(interaction.guild, top_users, RANKING_LIMIT)

            if not ranked:
                await interaction.followup.send("まだ誰もBumpしていません。君が最初のヒーローになろう！")
                return

            embed = discord.Embed(
                title="🏆 BUMPランキングボード TOP10 🏆",
                description=f"サーバー合計Bump: **{server_total}** 回！",
                color=discord.Color.gold(),
            )

            rank_emojis = ["🥇", "🥈", "🥉"] + [f"**{i}位**" for i in range(4, RANKING_LIMIT + 1)]

            for i, (record, name) in enumerate(ranked):
                bumps = record['bump_count']
                streak = record.get('current_streak', 0)
                title = get_bump_title(bumps)

                value = f"> **{bumps}** 回"
                if streak >= 3:
                    badge = get_streak_badge(streak)
                    value += f"　{badge}({streak}日連続)"

                embed.add_field(
                    name=f"{rank_emojis[i]} {name}　{title}",
                    value=value,
                    inline=False,
                )

            embed.set_footer(text="君のBumpが、このサーバーの歴史を創る！")
            await interaction.followup.send(embed=embed)

        except discord.NotFound:
            logging.warning("Interaction expired: bump_top")
        except Exception as e:
            logging.error(f"/bump_top エラー: {e}", exc_info=True)
            await _safe_error_reply(interaction, "ランキングの表示中にエラーが起きました。")

    @app_commands.command(name="bump_weekly", description="今週のBumpランキングを表示します。")
    async def bump_weekly(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            weekly = await db.get_weekly_top_users(RANKING_CANDIDATE_POOL)

            ranked = await self._resolve_ranked_users(interaction.guild, weekly, RANKING_LIMIT)

            if not ranked:
                await interaction.followup.send("今週はまだ誰もBumpしていません！")
                return

            embed = discord.Embed(
                title="📅 今週のBUMPランキング 📅",
                description="月曜日〜日曜日の集計",
                color=discord.Color.green(),
            )

            rank_emojis = ["🥇", "🥈", "🥉"] + [f"**{i}位**" for i in range(4, RANKING_LIMIT + 1)]

            for i, (record, name) in enumerate(ranked):
                bumps = record['bump_count']
                streak = record.get('current_streak', 0)

                value = f"> **{bumps}** 回"
                if streak >= 3:
                    value += f"　🔥{streak}日連続"

                embed.add_field(
                    name=f"{rank_emojis[i]} {name}",
                    value=value,
                    inline=False,
                )

            # 1位のユーザーをMVP表示
            try:
                mvp_id = ranked[0][0]['user_id']
                mvp = await self.bot.fetch_user(mvp_id)
                embed.set_thumbnail(url=mvp.display_avatar.url)
                embed.set_footer(text=f"🌟 今週のMVP: {ranked[0][1]}")
            except Exception:
                pass

            await interaction.followup.send(embed=embed)

        except discord.NotFound:
            logging.warning("Interaction expired: bump_weekly")
        except Exception as e:
            logging.error(f"/bump_weekly エラー: {e}", exc_info=True)
            await _safe_error_reply(interaction, "週間ランキングの表示中にエラーが起きました。")

    @app_commands.command(name="bump_user", description="指定したユーザーの詳細Bump統計を表示します。")
    async def bump_user(self, interaction: discord.Interaction, user: discord.User):
        try:
            await interaction.response.defer()
            stats = await db.get_user_stats(user.id)

            embed = discord.Embed(
                title=f"📊 {user.display_name} のBump統計",
                color=discord.Color.blue(),
            )
            embed.set_thumbnail(url=user.display_avatar.url)

            title = get_bump_title(stats['bump_count'])
            badge = get_streak_badge(stats['current_streak'])

            embed.add_field(name="称号", value=title, inline=True)
            embed.add_field(name="累計Bump", value=f"**{stats['bump_count']}** 回", inline=True)
            embed.add_field(name="今週", value=f"**{stats['weekly_count']}** 回", inline=True)
            embed.add_field(name="現在の連続", value=f"**{stats['current_streak']}** 日 {badge}", inline=True)
            embed.add_field(name="最長連続", value=f"**{stats['max_streak']}** 日", inline=True)

            await interaction.followup.send(embed=embed)

        except discord.NotFound:
            logging.warning("Interaction expired: bump_user")
        except Exception as e:
            logging.error(f"/bump_user エラー: {e}", exc_info=True)
            await _safe_error_reply(interaction, "統計の表示中にエラーが起きました。")

    @app_commands.command(name="bump_time", description="次のBumpリマインド時刻を表示します。")
    async def bump_time(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            reminder = await db.get_reminder()
            if reminder:
                remind_at = reminder['remind_at']
                await interaction.followup.send(
                    f"次のBumpが可能になるのは <t:{int(remind_at.timestamp())}:R> です。"
                )
            else:
                await interaction.followup.send("現在、リマインドは設定されていません。`/bump` をお願いします！")
        except discord.NotFound:
            logging.warning("Interaction expired: bump_time")
        except Exception as e:
            logging.error(f"/bump_time エラー: {e}", exc_info=True)
            await _safe_error_reply(interaction, "リマインド時刻の表示中にエラーが起きました。")


async def _safe_error_reply(interaction: discord.Interaction, text: str):
    """インタラクションの状態に応じて安全にエラーメッセージを送る"""
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(text, ephemeral=True)
        else:
            await interaction.followup.send(text)
    except discord.NotFound:
        logging.warning("Could not send error message - interaction expired")


async def setup(bot: commands.Bot):
    await bot.add_cog(RankingCog(bot))
