import time
from database import get_cursor
from utils.db_helpers import get_user_numbers_count

def check_referral(user_id):
    with get_cursor() as cur:
        cur.execute("SELECT referred_by FROM users WHERE id=%s", (user_id,))
        ref = cur.fetchone()
        
        if not ref or not ref[0]:
            return
        
        referrer_id = ref[0]
        
        cur.execute("""
        SELECT status FROM referrals 
        WHERE referrer_id=%s AND referred_id=%s
        """, (referrer_id, user_id))
        
        existing = cur.fetchone()
        if existing and existing[0] == 'qualified':
            return
        
        count = get_user_numbers_count(user_id)
        
        if count >= 2:
            cur.execute("""
            INSERT INTO referrals (referrer_id, referred_id, status, qualified_date)
            VALUES (%s, %s, 'qualified', %s)
            ON CONFLICT (referrer_id, referred_id) 
            DO UPDATE SET status='qualified', qualified_date=%s
            """, (referrer_id, user_id, int(time.time()), int(time.time())))
            
            cur.execute("""
            UPDATE users 
            SET referral_count = referral_count + 1,
                referral_balance = referral_balance + 1
            WHERE id=%s
            """, (referrer_id,))

def get_referral_info(user_id):
    with get_cursor() as cur:
        cur.execute("""
        SELECT referral_count, referral_balance FROM users WHERE id=%s
        """, (user_id,))
        return cur.fetchone()