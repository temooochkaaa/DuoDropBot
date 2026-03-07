import os
import logging
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor
from contextlib import contextmanager

from config import DATABASE_URL, DB_POOL_MIN, DB_POOL_MAX, DB_POOL_TIMEOUT, CLEANUP_DAYS

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.pool = None
        self.init_pool()
    
    def init_pool(self):
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                DB_POOL_MIN,
                DB_POOL_MAX,
                dsn=DATABASE_URL,
                cursor_factory=DictCursor,
                connect_timeout=DB_POOL_TIMEOUT
            )
            logger.info(f"Database pool created (min={DB_POOL_MIN}, max={DB_POOL_MAX})")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, commit=False):
        with self.get_connection() as conn:
            cur = conn.cursor()
            try:
                yield cur
                if commit:
                    conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database cursor error: {e}")
                raise
            finally:
                cur.close()
    
    def close_all(self):
        try:
            if self.pool:
                self.pool.closeall()
                logger.info("All database connections closed")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")

db_pool = DatabasePool()

def get_cursor(commit=False):
    return db_pool.get_cursor(commit)

def reorder_queue(platform=None):
    """Пересчет позиций в очереди"""
    with get_cursor(commit=True) as cur:
        if platform:
            cur.execute("""
            WITH numbered AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY created_at) as new_pos
                FROM numbers
                WHERE platform=%s AND status='waiting' AND in_queue=1
            )
            UPDATE numbers n
            SET queue_position = numbered.new_pos
            FROM numbered
            WHERE n.id = numbered.id
            """, (platform,))
        else:
            cur.execute("""
            WITH numbered AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY created_at) as new_pos
                FROM numbers
                WHERE status='waiting' AND in_queue=1
            )
            UPDATE numbers n
            SET queue_position = numbered.new_pos
            FROM numbered
            WHERE n.id = numbered.id
            """)

def cleanup_old_numbers():
    """Очистка старых cancelled номеров"""
    with get_cursor(commit=True) as cur:
        cur.execute("""
        DELETE FROM numbers
        WHERE status='cancelled'
        AND created_at < EXTRACT(EPOCH FROM NOW() - INTERVAL '%s days')
        """, (CLEANUP_DAYS,))
        deleted = cur.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old cancelled numbers")

def init_db():
    with get_cursor(commit=True) as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            role TEXT DEFAULT 'user',
            referred_by BIGINT,
            referral_count INTEGER DEFAULT 0,
            referral_balance REAL DEFAULT 0,
            accepted INTEGER DEFAULT 0,
            created_at BIGINT
        )
        """)
        
        cur.execute("""
        CREATE TABLE IF NOT EXISTS numbers (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            phone TEXT,
            platform TEXT,
            status TEXT,
            request_type TEXT,
            taken_by BIGINT,
            queue_position INTEGER,
            in_queue INTEGER DEFAULT 1,
            created_at BIGINT,
            code_sent_at BIGINT,
            code_entered_at BIGINT,
            activated_at BIGINT,
            crashed_at BIGINT,
            total_work_time INTEGER DEFAULT 0,
            code_photo_id TEXT,
            qr_photo_id TEXT,
            code_text TEXT,
            waiting_for_code INTEGER DEFAULT 0,
            waiting_for_extra INTEGER DEFAULT 0,
            extra_request TEXT,
            last_extra_request BIGINT,
            last_queue_notification BIGINT,
            retry_count INTEGER DEFAULT 0
        )
        """)
        
        cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT,
            referred_id BIGINT,
            status TEXT DEFAULT 'pending',
            qualified_date BIGINT
        )
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_numbers_status ON numbers(status, taken_by)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_numbers_user ON numbers(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_numbers_queue ON numbers(queue_position)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_numbers_phone ON numbers(phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_numbers_platform ON numbers(platform)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_numbers_status_inqueue ON numbers(status, in_queue)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_numbers_last_notification ON numbers(last_queue_notification)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_numbers_created ON numbers(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_referred ON users(referred_by)")
        
        logger.info("Database initialized successfully")