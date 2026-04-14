# cogs/admin.py - 管理者用コマンド

import discord
from discord.ext import commands
from discord import app_commands
import logging
import database as db
from config import DISBOARD_BOT_ID


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="scan_history",
        description="【管理者用/一度きり】過去のBump履歴をスキャンして登録します。",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def scan_history(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 10000] = 1000,
    ):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)

            if await db.is_scan_completed():
                await interaction.followup.send(
                    "**エラー：過去ログのスキャンは既に完了しています！**", ephemeral=True
                )
                return

            found_bumps = 0
            async for message in interaction.channel.history(limit=limit):
                user_id = _extract_bump_user_id(message)
                if user_id is not None:
                    await db.record_bump(user_id)
                    found_bumps += 1

            if found_bumps == 0:
                await interaction.followup.send(
                    f"{limit}件のメッセージをスキャンしましたが、Bump履歴は見つかりませんでした。",
                    ephemeral=True,
                )
                return

            await db.mark_scan_as_completed()
            await interaction.followup.send(
                f"スキャン完了！**{found_bumps}件**のBumpを記録しました。\n**安全装置が作動しました。**",
                ephemeral=True,
            )

        except Exception as e:
            logging.error(f"scan_history エラー: {e}", exc_info=True)
            await _safe_error_reply(interaction, "スキャン中にエラーが発生しました。しばらく待ってから再試行してください。")

    @scan_history.error
    async def on_scan_history_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await _safe_error_reply(interaction, "このコマンドはサーバーの管理者しか使えません。")
        else:
            logging.error(f"scan_history コマンドエラー: {error}", exc_info=True)
            await _safe_error_reply(interaction, "スキャン中にエラーが発生しました。しばらく待ってから再試行してください。")


def _extract_bump_user_id(message: discord.Message):
    """メッセージからBumpしたユーザーのIDを抽出。Bumpでなければ None"""
    if message.author.id != DISBOARD_BOT_ID:
        return None

    meta = getattr(message, 'interaction_metadata', None)
    if meta is not None:
        name = getattr(meta, 'name', None) or getattr(meta, 'command_name', None)
        if name == 'bump' or (name is None and hasattr(meta, 'user')):
            user = getattr(meta, 'user', None)
            return user.id if user else None

    old = getattr(message, 'interaction', None)
    if old is not None and getattr(old, 'name', None) == 'bump':
        user = getattr(old, 'user', None)
        return user.id if user else None

    return None


async def _safe_error_reply(interaction: discord.Interaction, text: str):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(text, ephemeral=True)
        else:
            await interaction.followup.send(text, ephemeral=True)
    except discord.NotFound:
        logging.warning("エラーメッセージ送信失敗: interaction期限切れ")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
