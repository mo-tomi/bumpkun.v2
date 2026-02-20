# 【最終決定版】SupabaseのSSL接続に対応した database.py
import os
import asyncpg
import datetime
import ssl # SSLヘルメットを使うためにインポート！

# ### 共通で使う道具（関数） ###
DATABASE_URL = os.environ.get('DATABASE_URL')

# グローバル接続プール（一度作成したら再利用する）
_global_pool = None

# --- 修正箇所：グローバル接続プールを使用してタイムアウト問題を解決 ---
async def get_pool():
    """グローバル接続プールを取得または作成する関数"""
    global _global_pool
    
    # すでにプールが作成されている場合はそれを返す
    if _global_pool is not None:
        return _global_pool
    
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    
    # Supabaseの頑固な警備員を突破するための、特別なSSL設定を作成する
    # これは「暗号化は必須だけど、証明書の細かいチェックはしなくていいよ」というおまじない
    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    # Supabase環境に最適化された接続設定（タイムアウト問題を解決するための設定）
    try:
        _global_pool = await asyncpg.create_pool(
            dsn=DATABASE_URL, 
            ssl=ctx,
            # pgBouncer環境での準備済みステートメント重複エラーを回避
            statement_cache_size=0,
            # 接続タイムアウト設定（30秒で接続できなければエラー）
            timeout=30,
            # 接続プールの設定
            min_size=1,      # 最小接続数
            max_size=10,     # 最大接続数
            # コマンドタイムアウト設定（60秒でSQLコマンドがタイムアウト）
            command_timeout=60
        )
        print("✅ グローバルデータベース接続プールを作成しました")
        return _global_pool
    except Exception as e:
        # 接続エラーの詳細をログに出力（デバッグ用）
        print(f"❌ データベース接続エラーが発生しました: {e}")
        raise e

async def close_pool():
    """アプリケーション終了時にグローバル接続プールを閉じる関数"""
    global _global_pool
    if _global_pool is not None:
        try:
            await _global_pool.close()
            print("✅ グローバルデータベース接続プールを閉じました")
        except Exception as e:
            print(f"⚠️ 接続プール終了時のエラー: {e}")
        finally:
            _global_pool = None
# #################################


# --- BUMPくん用の関数 (この下は一切変更なし！) ---
async def init_db():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                bump_count INTEGER NOT NULL DEFAULT 0
            );
        ''')
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                remind_at TIMESTAMP WITH TIME ZONE NOT NULL,
                status TEXT NOT NULL DEFAULT 'waiting'
            );
        ''')
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        ''')
        await connection.execute('''
            INSERT INTO settings (key, value) VALUES ('scan_completed', 'false')
            ON CONFLICT (key) DO NOTHING;
        ''')
    # グローバルプールを使用するため、個別にcloseしない

async def is_scan_completed():
    pool = await get_pool()
    async with pool.acquire() as connection:
        record = await connection.fetchrow("SELECT value FROM settings WHERE key = 'scan_completed'")
    # グローバルプールを使用するため、個別にcloseしない
    return record and record['value'] == 'true'

async def mark_scan_as_completed():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute("UPDATE settings SET value = 'true' WHERE key = 'scan_completed'")
    # グローバルプールを使用するため、個別にcloseしない

async def record_bump(user_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('''
            INSERT INTO users (user_id, bump_count) VALUES ($1, 1)
            ON CONFLICT (user_id) DO UPDATE SET bump_count = users.bump_count + 1;
        ''', user_id)
        count = await connection.fetchval('SELECT bump_count FROM users WHERE user_id = $1', user_id)
    # グローバルプールを使用するため、個別にcloseしない
    return count

async def get_top_users(limit=5):
    pool = await get_pool()
    async with pool.acquire() as connection:
        records = await connection.fetch(
            'SELECT user_id, bump_count FROM users ORDER BY bump_count DESC LIMIT $1', limit
        )
    # グローバルプールを使用するため、個別にcloseしない
    return records

async def get_user_count(user_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        count = await connection.fetchval('SELECT bump_count FROM users WHERE user_id = $1', user_id)
    # グローバルプールを使用するため、個別にcloseしない
    return count or 0

async def set_reminder(channel_id, remind_time):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('DELETE FROM reminders')
        await connection.execute('INSERT INTO reminders (channel_id, remind_at) VALUES ($1, $2)', channel_id, remind_time)
    # グローバルプールを使用するため、個別にcloseしない

async def get_reminder():
    pool = await get_pool()
    async with pool.acquire() as connection:
        record = await connection.fetchrow(
            'SELECT channel_id, remind_at, status FROM reminders ORDER BY remind_at LIMIT 1'
        )
    # グローバルプールを使用するため、個別にcloseしない
    return record

async def update_reminder_status(channel_id, new_status):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            'UPDATE reminders SET status = $1 WHERE channel_id = $2', new_status, channel_id
        )
    # グローバルプールを使用するため、個別にcloseしない

async def clear_reminder():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('DELETE FROM reminders')
    # グローバルプールを使用するため、個別にcloseしない

async def get_total_bumps():
    pool = await get_pool()
    async with pool.acquire() as connection:
        total = await connection.fetchval('SELECT SUM(bump_count) FROM users')
    # グローバルプールを使用するため、個別にcloseしない
    return total or 0


# --- 自己紹介Bot用の関数 (v2仕様) ---
# ... (このセクションは変更なし) ...
async def init_intro_bot_db():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS introductions (
                user_id BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL
            );
        ''')
    # グローバルプールを使用するため、個別にcloseしない
async def save_intro(user_id, channel_id, message_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('''
            INSERT INTO introductions (user_id, channel_id, message_id) VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET channel_id = $2, message_id = $3;
        ''', user_id, channel_id, message_id)
    # グローバルプールを使用するため、個別にcloseしない
async def get_intro_ids(user_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        record = await connection.fetchrow(
            "SELECT channel_id, message_id FROM introductions WHERE user_id = $1", user_id
        )
    # グローバルプールを使用するため、個別にcloseしない
    return record

# --- 守護神ボット用の関数 ---
# ... (このセクションは変更なし) ...
async def init_shugoshin_db():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                report_id SERIAL PRIMARY KEY, guild_id BIGINT, message_id BIGINT,
                target_user_id BIGINT, violated_rule TEXT, details TEXT,
                message_link TEXT, urgency TEXT, status TEXT DEFAULT '未対応',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                report_channel_id BIGINT,
                urgent_role_id BIGINT
            );
        ''')
        await connection.execute('''
            CREATE TABLE IF NOT EXISTS report_cooldowns (
                user_id BIGINT PRIMARY KEY,
                last_report_at TIMESTAMP WITH TIME ZONE NOT NULL
            );
        ''')
    # グローバルプールを使用するため、個別にcloseしない
async def setup_guild(guild_id, report_channel_id, urgent_role_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute('''
            INSERT INTO guild_settings (guild_id, report_channel_id, urgent_role_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
            SET report_channel_id = $2, urgent_role_id = $3;
        ''', guild_id, report_channel_id, urgent_role_id)
    # グローバルプールを使用するため、個別にcloseしない
async def get_guild_settings(guild_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        settings = await connection.fetchrow(
            "SELECT report_channel_id, urgent_role_id FROM guild_settings WHERE guild_id = $1",
            guild_id
        )
    # グローバルプールを使用するため、個別にcloseしない
    return settings
async def check_cooldown(user_id, cooldown_seconds):
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            record = await connection.fetchrow(
                "SELECT last_report_at FROM report_cooldowns WHERE user_id = $1", user_id
            )
            now = datetime.datetime.now(datetime.timezone.utc)
            if record:
                time_since_last = now - record['last_report_at']
                if time_since_last.total_seconds() < cooldown_seconds:
                    return cooldown_seconds - time_since_last.total_seconds()
            await connection.execute('''
                INSERT INTO report_cooldowns (user_id, last_report_at) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET last_report_at = $2;
            ''', user_id, now)
            return 0
    # グローバルプールを使用するため、個別にcloseしない
async def create_report(guild_id, target_user_id, violated_rule, details, message_link, urgency):
    pool = await get_pool()
    async with pool.acquire() as connection:
        report_id = await connection.fetchval(
            '''INSERT INTO reports (guild_id, target_user_id, violated_rule, details, message_link, urgency) 
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING report_id''',
            guild_id, target_user_id, violated_rule, details, message_link, urgency
        )
    # グローバルプールを使用するため、個別にcloseしない
    return report_id
async def update_report_message_id(report_id, message_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE reports SET message_id = $1 WHERE report_id = $2",
            message_id, report_id
        )
    # グローバルプールを使用するため、個別にcloseしない
async def update_report_status(report_id, new_status):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE reports SET status = $1 WHERE report_id = $2",
            new_status, report_id
        )
    # グローバルプールを使用するため、個別にcloseしない
async def get_report(report_id):
    pool = await get_pool()
    async with pool.acquire() as connection:
        record = await connection.fetchrow("SELECT * FROM reports WHERE report_id = $1", report_id)
    # グローバルプールを使用するため、個別にcloseしない
    return record
async def list_reports(status_filter=None):
    pool = await get_pool()
    query = "SELECT report_id, target_user_id, status FROM reports"
    params = []
    if status_filter and status_filter != 'all':
        query += " WHERE status = $1"
        params.append(status_filter)
    query += " ORDER BY report_id DESC LIMIT 20"
    async with pool.acquire() as connection:
        records = await connection.fetch(query, *params)
    # グローバルプールを使用するため、個別にcloseしない
    return records
async def get_report_stats():
    pool = await get_pool()
    async with pool.acquire() as connection:
        stats = await connection.fetch('''
            SELECT status, COUNT(*) as count 
            FROM reports 
            GROUP BY status
        ''')
    # グローバルプールを使用するため、個別にcloseしない
    return {row['status']: row['count'] for row in stats}