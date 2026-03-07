from functools import lru_cache
from database import get_cursor

@lru_cache(maxsize=128)
def get_queue_count(platform: str, timeout: int = 60) -> int:
    with get_cursor() as cur:
        cur.execute("""
        SELECT COUNT(*) FROM numbers 
        WHERE platform=%s AND status='waiting' AND in_queue=1
        """, (platform,))
        return cur.fetchone()[0]

def get_user_numbers_count(user_id: int) -> int:
    with get_cursor() as cur:
        cur.execute("""
        SELECT COUNT(*) FROM numbers 
        WHERE user_id=%s AND status IN ('waiting', 'in_progress')
        """, (user_id,))
        return cur.fetchone()[0]