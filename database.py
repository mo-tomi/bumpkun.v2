import os
import asyncpg
import datetime

DATABASE_URL = os.environ.get('DATABASE_URL')

async def get_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as connection:
        # ユーザーごとのbump回数を保存するテーブル
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                bump_count INTEGER NOT NULL DEFAULT 0
            );
        ''')
        # 次のリマインド時刻を保存するテーブル
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                remind_at TIMESTAMP WITH TIME ZONE NOT NULL
            );
        ''')
        # ★★★ここからが新しい部分★★★
        # Botの設定を保存するテーブル
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        ''')
        # 初回スキャンが完了したかどうかの初期値を設定
        await connection.execute('''
            INSERT INTO settings (key, value) VALUES ('scan_completed', 'false')
            ON CONFLICT (key) DO NOTHING;
        ''')
        # ★★★ここまで★★★
    await pool.close()
    print("データベースの初期化が完了しました。")

# ★★★ここからが新しい関数★★★
async def is_scan_completed():
    """過去ログのスキャンが完了したか確認する"""
    pool = await get_pool()
    async with pool.acquire() as connection:
        record = await connection.fetchrow("SELECT value FROM settings WHERE key = 'scan_completed'")
    await pool.close()
    return record['value'] == 'true'

async def mark_scan_as_completed():
    """過去ログのスキャンを完了としてマークする"""
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute("UPDATE settings SET value = 'true' WHERE key = 'scan_completed'")
    await pool.close()
# ★★★ここまで★★★

# record_bump, get_top_users, get_user_count, set_reminder, get_reminder, clear_reminder は変更なし
async def record_bump(user_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('''
            INSERT INTO users (user_id, bump_count) VALUES ($1, 1)
            ON CONFLICT (user_id) DO UPDATE SET bump_count = users.bump_count + 1;
        ''', user_id)
        count = await connection.fetchval('SELECT bump_count FROM users WHERE user_id = $1', user_id)
    await pool.close()
    return count

async def get_top_users():
    pool = await get_pool()
    async with pool.acquire() as connection:
        records = await connection.fetch('SELECT user_id, bump_count FROM users ORDER BY bump_count DESC LIMIT 5')
    await pool.close()
    return records

async def get_user_count(user_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        count = await connection.fetchval('SELECT bump_count FROM users WHERE user_id = $1', user_id)
    await pool.close()
    return count or 0

async def set_reminder(channel_id, remind_time):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('DELETE FROM reminders')
        await connection.execute('INSERT INTO reminders (channel_id, remind_at) VALUES ($1, $2)', channel_id, remind_time)
    await pool.close()

async def get_reminder():
    pool = await get_pool()
    async with pool.acquire() as connection:
        record = await connection.fetchrow('SELECT channel_id, remind_at FROM reminders ORDER BY remind_at LIMIT 1')
    await pool.close()
    return record

async def clear_reminder():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('DELETE FROM reminders')
    await pool.close()
