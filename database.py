import os
import asyncpg
import datetime

# データベース接続情報を環境変数から取得
DATABASE_URL = os.environ.get('DATABASE_URL')

# データベースに接続するための非同期関数
async def get_pool():
    return await asyncpg.create_pool(DATABASE_URL)

# データベースの初期設定（テーブルがなければ作る）
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
    await pool.close()
    print("データベースの初期化が完了しました。")

# Bumpを記録する関数
async def record_bump(user_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        # ユーザーが存在すればカウントを1増やし、存在しなければ新しく作る
        await connection.execute('''
            INSERT INTO users (user_id, bump_count) VALUES ($1, 1)
            ON CONFLICT (user_id) DO UPDATE SET bump_count = users.bump_count + 1;
        ''', user_id)
        
        # 更新後のカウント数を取得して返す
        count = await connection.fetchval('SELECT bump_count FROM users WHERE user_id = $1', user_id)
    await pool.close()
    return count

# ランキング上位5人を表示する関数
async def get_top_users():
    pool = await get_pool()
    async with pool.acquire() as connection:
        records = await connection.fetch('SELECT user_id, bump_count FROM users ORDER BY bump_count DESC LIMIT 5')
    await pool.close()
    return records

# 特定ユーザーのbump回数を取得する関数
async def get_user_count(user_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        count = await connection.fetchval('SELECT bump_count FROM users WHERE user_id = $1', user_id)
    await pool.close()
    return count or 0

# リマインダーを設定する関数
async def set_reminder(channel_id, remind_time):
    pool = await get_pool()
    async with pool.acquire() as connection:
        # 既存のリマインダーは一旦すべて消す（通常は1つしかないはず）
        await connection.execute('DELETE FROM reminders')
        # 新しいリマインダーを登録
        await connection.execute('INSERT INTO reminders (channel_id, remind_at) VALUES ($1, $2)', channel_id, remind_time)
    await pool.close()

# 設定されているリマインダーを取得する関数
async def get_reminder():
    pool = await get_pool()
    async with pool.acquire() as connection:
        record = await connection.fetchrow('SELECT channel_id, remind_at FROM reminders ORDER BY remind_at LIMIT 1')
    await pool.close()
    return record

# リマインダーを削除する関数
async def clear_reminder():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('DELETE FROM reminders')
    await pool.close()