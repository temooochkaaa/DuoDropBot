import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor
from utils.helpers import safe_send_message  # Вместо from main import ...

def check_queue_job(context):
    now = int(time.time())
    five_min_ago = now - 300
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT user_id, array_agg(phone) as phones, array_agg(id) as ids
        FROM numbers 
        WHERE status='waiting' AND in_queue=1 AND taken_by IS NULL
        AND (last_queue_notification IS NULL OR last_queue_notification < %s)
        GROUP BY user_id
        LIMIT 5
        """, (five_min_ago,))
        
        rows = cur.fetchall()
        
        for user_id, phones, ids in rows:
            phone_list = "\n".join([f"• {p}" for p in phones])
            text = f"⏳ Ваши номера всё ещё в очереди:\n{phone_list}\n\nОставить все?"
            
            buttons = []
            for nid in ids:
                buttons.append([
                    InlineKeyboardButton(f"✅ Оставить #{nid}", callback_data=f"keep_{nid}"),
                    InlineKeyboardButton(f"❌ Убрать #{nid}", callback_data=f"remove_{nid}")
                ])
            
            safe_send_message(
                context.bot, user_id,
                text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
            cur.execute("""
            UPDATE numbers SET last_queue_notification=%s 
            WHERE id = ANY(%s)
            """, (now, ids))

def queue_action(update, context):
    query = update.callback_query
    query.answer()
    
    data = query.data.split("_")
    action = data[0]
    number_id = int(data[1])
    user_id = query.from_user.id
    
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT platform, taken_by FROM numbers WHERE id=%s AND user_id=%s", (number_id, user_id))
        result = cur.fetchone()
        
        if not result:
            safe_edit_message(query, "❌ Номер не найден.")
            return
        
        platform, taken_by = result
        
        if taken_by is not None:
            safe_edit_message(query, "❌ Номер уже взят холодкой и не может быть удален.")
            return
        
        if action == "remove":
            cur.execute("""
            UPDATE numbers SET status='cancelled', in_queue=0, taken_by=NULL WHERE id=%s AND user_id=%s
            """, (number_id, user_id))
            safe_edit_message(query, "❌ Номер убран из очереди.")
            
            from database import reorder_queue
            reorder_queue(platform)
            logger.info(f"Number {number_id} removed from queue by user {user_id}")
        else:
            safe_edit_message(query, "✅ Номер остаётся в очереди.")