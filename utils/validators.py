from database import get_cursor
from config import MIN_PHONE_LENGTH, MAX_PHONE_LENGTH

def validate_phone(phone):
    return phone.isdigit() and MIN_PHONE_LENGTH <= len(phone) <= MAX_PHONE_LENGTH

def check_duplicate(user_id, phone, platform):
    with get_cursor() as cur:
        cur.execute("""
        SELECT id, status FROM numbers 
        WHERE user_id=%s AND phone=%s AND platform=%s 
        AND status IN ('waiting', 'in_progress', 'code_sent', 'code_entered', 'activated')
        """, (user_id, phone, platform))
        
        return cur.fetchone()

def can_submit_again(status):
    return status in ['failed', 'crashed', 'cancelled']