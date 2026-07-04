# config.py - 設定値を一箇所にまとめる

import os
from dotenv import load_dotenv

load_dotenv()

# --- Bot設定 ---
TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
PORT = int(os.environ.get('PORT', 10000))

# --- DISBOARD ---
DISBOARD_BOT_ID = 302050872383242240
BUMP_COOLDOWN_HOURS = 2

# --- ランキング ---
RANKING_LIMIT = 10  # v2では5だったのを10に拡張

# ランキングから除外する表示名(削除済みアカウントは自動で除外されます)
RANKING_EXCLUDED_NAMES = ["もちづき"]

# --- スロットマシン(2種類からランダム) ---
SLOT_MACHINES = [
    {
        "name": "ノーマルスロット",
        "reels": ['💎', '⭐', '🔔', '🍀', '🎯', '🌈'],
        "jackpot_messages": {
            '💎': "🎉🎉🎉 **JACKPOT!!** 🎉🎉🎉\n奇跡の **ダイヤモンド揃い**！伝説の運の持ち主だ！",
            '⭐': "🎊🎊 **BIG WIN!** 🎊🎊\n見事な **スター揃い**！今日は最高の1日になるぞ！",
            '🔔': "🔔 **WIN!** 🔔\nラッキーな **ベル揃い**！ささやかな幸せ！",
            '🍀': "🍀 **LUCKY WIN!** 🍀\n**四つ葉のクローバー揃い**！幸運が舞い込む！",
            '🎯': "🎯 **BULLS EYE!** 🎯\n的中！**ターゲット揃い**！狙い通り！",
            '🌈': "🌈 **RAINBOW WIN!** 🌈\n**レインボー揃い**！虹の彼方に幸せが！",
        },
    },
    {
        "name": "フルーツスロット",
        "reels": ['🍒', '🍋', '🍇', '7️⃣', '🔥', '💰'],
        "jackpot_messages": {
            '🍒': "🍒🍒🍒 **CHERRY MASTER!!** 🍒🍒🍒\n真紅の **チェリー揃い**！甘い勝利の予感！",
            '🍋': "🍋🍋 **LEMON SPLASH!** 🍋🍋\n爽やかな **レモン揃い**！気分爽快な1日に！",
            '🍇': "🍇 **GRAPE RUSH!** 🍇\n芳醇な **グレープ揃い**！実り多き幸運！",
            '7️⃣': "7️⃣7️⃣7️⃣ **LUCKY SEVEN!!** 7️⃣7️⃣7️⃣\n伝説の **セブン揃い**！最強の幸運を掴んだ！",
            '🔥': "🔥🔥 **BLAZING WIN!** 🔥🔥\n燃え盛る **フレイム揃い**！情熱が弾ける！",
            '💰': "💰💰💰 **MONEY RAIN!!** 💰💰💰\n黄金の **マネー揃い**！大金運が舞い込む！",
        },
    },
]

# --- 称号 (bump_count → 称号) ---
BUMP_TITLES = [
    (1000, "BUMPの創造主♾️"),
    (500,  "BUMPの化身🌌"),
    (300,  "BUMPの伝説🐉"),
    (200,  "BUMPの神様⛩️"),
    (150,  "BUMPの英雄王👑"),
    (100,  "BUMPの英雄👑"),
    (50,   "BUMPの達人✨"),
    (10,   "BUMPの常連⭐"),
    (0,    "BUMPの新人🔰"),
]

# --- 連続記録(Streak)の称号 ---
STREAK_BADGES = [
    (30, "🔥炎の30日連続🔥"),
    (14, "⚡2週間連続⚡"),
    (7,  "🌟1週間連続🌟"),
    (3,  "✨3日連続✨"),
    (0,  ""),
]

# --- お礼メッセージ ---
THANKS_MESSAGES = [
    "最高のBumpをありがとう！君はサーバーの希望だ！",
    "ナイスBump！この調子でサーバーを盛り上げていこう！",
    "君のBumpが、サーバーを次のステージへ押し上げる！サンキュー！",
    "お疲れ様！君の貢献に心から感謝するよ！",
    "Bump完了！サーバーがまた一歩前進したよ！",
    "いつもBumpしてくれて本当にありがとう！",
]

# --- マイルストーン ---
MILESTONES = [10, 50, 100, 150, 200, 300, 500, 1000]


def get_bump_title(count: int) -> str:
    """Bump回数から称号を取得"""
    for threshold, title in BUMP_TITLES:
        if count >= threshold:
            return title
    return "BUMPの新人🔰"


def get_streak_badge(streak: int) -> str:
    """連続日数からバッジを取得"""
    for threshold, badge in STREAK_BADGES:
        if streak >= threshold:
            return badge
    return ""

async def setup(bot: commands.Bot):
    await bot.add_cog(BumpCog(bot))
