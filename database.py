# database.py - v3: 連続記録(Streak)・週間MVP対応

import os
import asyncpg
import datetime
import ssl
import logging
from config import DATABASE_URL

_global_pool = None


async def get_pool():
    """グローバル接続プールを取得または作成"""
    global _global_pool
    if _global_pool is not None:
        return _global_pool

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")

    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        _global_pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            ssl=ctx,
            statement_cache_size=0,
            timeout=30,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
        logging.info("✅ グローバルDB接続プール作成完了")
        return _global_pool
    except Exception as e:
        logging.error(f"❌ DB接続エラー: {e}")
        raise


async def close_pool():
    """接続プールを閉じる"""
    global _global_pool
    if _global_pool is not None:
        try:
            await _global_pool.close()
            logging.info("✅ DB接続プール終了")
        except Exception as e:
            logging.error(f"⚠️ プール終了エラー: {e}")
        finally:
            _global_pool = None


# ===========================
# 初期化
# ===========================

async def init_db():
    """テーブルを作成（v3: streak列・weekly_bumpsテーブル追加）"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # usersテーブル（v3: streak追加）
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                bump_count INTEGER NOT NULL DEFAULT 0,
                last_bump_date DATE,
                current_streak INTEGER NOT NULL DEFAULT 0,
                max_streak INTEGER NOT NULL DEFAULT 0
            );
        ''')

        # v2からの移行: 既存テーブルにstreak列がなければ追加
        await conn.execute('''
            DO $$ BEGIN
                ALTER TABLE users ADD COLUMN IF NOT EXISTS last_bump_date DATE;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS current_streak INTEGER NOT NULL DEFAULT 0;
                ALTER TABLE users ADD COLUMN IF NOT EXISTS max_streak INTEGER NOT NULL DEFAULT 0;
            EXCEPTION WHEN OTHERS THEN NULL;
            END $$;
        ''')

        # 週間Bumpテーブル（v3新規）
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS weekly_bumps (
                user_id BIGINT NOT NULL,
                week_start DATE NOT NULL,
                bump_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, week_start)
            );
        ''')

        # リマインダー
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                remind_at TIMESTAMP WITH TIME ZONE NOT NULL,
                status TEXT NOT NULL DEFAULT 'waiting'
            );
        ''')

        # 設定
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        ''')
        await conn.execute('''
            INSERT INTO settings (key, value) VALUES ('scan_completed', 'false')
            ON CONFLICT (key) DO NOTHING;
        ''')


# ===========================
# Bump記録（v3: streak・週間カウント対応）
# ===========================

async def record_bump(user_id: int) -> dict:
    """
    Bumpを記録し、streak・週間カウントも更新する。
    戻り値: {
        'bump_count': int,      # 累計Bump回数
        'current_streak': int,  # 現在の連続日数
        'max_streak': int,      # 最大連続日数
        'weekly_count': int,    # 今週のBump回数
        'is_new_streak_record': bool  # 自己ベスト更新か
    }
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            today = datetime.date.today()

            # 週の開始日（月曜日基準）
            week_start = today - datetime.timedelta(days=today.weekday())

            # ユーザーの現在データを取得
            row = await conn.fetchrow(
                'SELECT bump_count, last_bump_date, current_streak, max_streak FROM users WHERE user_id = $1',
                user_id
            )

            if row:
                old_count = row['bump_count']
                last_date = row['last_bump_date']
                streak = row['current_streak']
                max_streak = row['max_streak']

                # Streak計算
                if last_date is not None:
                    days_diff = (today - last_date).days
                    if days_diff == 1:
                        # 昨日もBumpした → 連続日数+1
                        streak += 1
                    elif days_diff == 0:
                        # 同じ日に複数回Bump → streakは変えない
                        pass
                    else:
                        # 2日以上空いた → リセット
                        streak = 1
                else:
                    streak = 1

                new_count = old_count + 1
                is_new_record = streak > max_streak
                new_max = max(streak, max_streak)

                await conn.execute('''
                    UPDATE users SET
                        bump_count = $1,
                        last_bump_date = $2,
                        current_streak = $3,
                        max_streak = $4
                    WHERE user_id = $5
                ''', new_count, today, streak, new_max, user_id)

            else:
                # 新規ユーザー
                new_count = 1
                streak = 1
                new_max = 1
                is_new_record = True

                await conn.execute('''
                    INSERT INTO users (user_id, bump_count, last_bump_date, current_streak, max_streak)
                    VALUES ($1, 1, $2, 1, 1)
                ''', user_id, today)

            # 週間Bumpカウントを更新
            await conn.execute('''
                INSERT INTO weekly_bumps (user_id, week_start, bump_count)
                VALUES ($1, $2, 1)
                ON CONFLICT (user_id, week_start) DO UPDATE
                SET bump_count = weekly_bumps.bump_count + 1;
            ''', user_id, week_start)

            weekly_count = await conn.fetchval(
                'SELECT bump_count FROM weekly_bumps WHERE user_id = $1 AND week_start = $2',
                user_id, week_start
            )

            return {
                'bump_count': new_count,
                'current_streak': streak,
                'max_streak': new_max,
                'weekly_count': weekly_count or 1,
                'is_new_streak_record': is_new_record and streak > 1,
            }


# ===========================
# ランキング
# ===========================

async def get_top_users(limit=10):
    """累計ランキング（v3: デフォルト10位まで）"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            'SELECT user_id, bump_count, current_streak, max_streak FROM users ORDER BY bump_count DESC LIMIT $1',
            limit
        )


async def get_weekly_top_users(limit=10):
    """今週のランキング"""
    pool = await get_pool()
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    async with pool.acquire() as conn:
        return await conn.fetch(
            '''SELECT w.user_id, w.bump_count, u.current_streak
               FROM weekly_bumps w
               JOIN users u ON w.user_id = u.user_id
               WHERE w.week_start = $1
               ORDER BY w.bump_count DESC LIMIT $2''',
            week_start, limit
        )


async def get_user_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval('SELECT bump_count FROM users WHERE user_id = $1', user_id)
        return count or 0


async def get_user_stats(user_id: int) -> dict:
    """ユーザーの詳細統計を取得"""
    pool = await get_pool()
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT bump_count, current_streak, max_streak FROM users WHERE user_id = $1',
            user_id
        )
        weekly = await conn.fetchval(
            'SELECT bump_count FROM weekly_bumps WHERE user_id = $1 AND week_start = $2',
            user_id, week_start
        )
        if row:
            return {
                'bump_count': row['bump_count'],
                'current_streak': row['current_streak'],
                'max_streak': row['max_streak'],
                'weekly_count': weekly or 0,
            }
        return {'bump_count': 0, 'current_streak': 0, 'max_streak': 0, 'weekly_count': 0}


async def get_total_bumps() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval('SELECT SUM(bump_count) FROM users')
        return total or 0


# ===========================
# リマインダー
# ===========================

async def set_reminder(channel_id: int, remind_time: datetime.datetime):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM reminders')
        await conn.execute(
            'INSERT INTO reminders (channel_id, remind_at) VALUES ($1, $2)',
            channel_id, remind_time
        )


async def get_reminder():
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            'SELECT channel_id, remind_at, status FROM reminders ORDER BY remind_at LIMIT 1'
        )


async def update_reminder_status(channel_id: int, new_status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE reminders SET status = $1 WHERE channel_id = $2',
            new_status, channel_id
        )


async def clear_reminder():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM reminders')


# ===========================
# スキャン管理
# ===========================

async def is_scan_completed() -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow("SELECT value FROM settings WHERE key = 'scan_completed'")
        return record and record['value'] == 'true'


async def mark_scan_as_completed():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE settings SET value = 'true' WHERE key = 'scan_completed'")


# ===========================
# 自己紹介Bot用（v2互換）
# ===========================

async def init_intro_bot_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS introductions (
                user_id BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL
            );
        ''')


async def save_intro(user_id, channel_id, message_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO introductions (user_id, channel_id, message_id) VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET channel_id = $2, message_id = $3;
        ''', user_id, channel_id, message_id)


async def get_intro_ids(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT channel_id, message_id FROM introductions WHERE user_id = $1", user_id
        )


# ===========================
# 守護神ボット用（v2互換）
# ===========================

async def init_shugoshin_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                report_id SERIAL PRIMARY KEY, guild_id BIGINT, message_id BIGINT,
                target_user_id BIGINT, violated_rule TEXT, details TEXT,
                message_link TEXT, urgency TEXT, status TEXT DEFAULT '未対応',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                report_channel_id BIGINT,
                urgent_role_id BIGINT
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS report_cooldowns (
                user_id BIGINT PRIMARY KEY,
                last_report_at TIMESTAMP WITH TIME ZONE NOT NULL
            );
        ''')


async def setup_guild(guild_id, report_channel_id, urgent_role_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO guild_settings (guild_id, report_channel_id, urgent_role_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET report_channel_id = $2, urgent_role_id = $3;
        ''', guild_id, report_channel_id, urgent_role_id)


async def get_guild_settings(guild_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT report_channel_id, urgent_role_id FROM guild_settings WHERE guild_id = $1",
            guild_id
        )


async def check_cooldown(user_id, cooldown_seconds):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            record = await conn.fetchrow(
                "SELECT last_report_at FROM report_cooldowns WHERE user_id = $1", user_id
            )
            now = datetime.datetime.now(datetime.timezone.utc)
            if record:
                time_since_last = now - record['last_report_at']
                if time_since_last.total_seconds() < cooldown_seconds:
                    return cooldown_seconds - time_since_last.total_seconds()
            await conn.execute('''
                INSERT INTO report_cooldowns (user_id, last_report_at) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET last_report_at = $2;
            ''', user_id, now)
            return 0


async def create_report(guild_id, target_user_id, violated_rule, details, message_link, urgency):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            '''INSERT INTO reports (guild_id, target_user_id, violated_rule, details, message_link, urgency)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING report_id''',
            guild_id, target_user_id, violated_rule, details, message_link, urgency
        )


async def update_report_message_id(report_id, message_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE reports SET message_id = $1 WHERE report_id = $2", message_id, report_id
        )


async def update_report_status(report_id, new_status):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE reports SET status = $1 WHERE report_id = $2", new_status, report_id
        )


async def get_report(report_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM reports WHERE report_id = $1", report_id)


async def list_reports(status_filter=None):
    pool = await get_pool()
    query = "SELECT report_id, target_user_id, status FROM reports"
    params = []
    if status_filter and status_filter != 'all':
        query += " WHERE status = $1"
        params.append(status_filter)
    query += " ORDER BY report_id DESC LIMIT 20"
    async with pool.acquire() as conn:
        return await conn.fetch(query, *params)


async def get_report_stats():
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = await conn.fetch('''
            SELECT status, COUNT(*) as count FROM reports GROUP BY status
        ''')
        return {row['status']: row['count'] for row in stats}
