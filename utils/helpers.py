import logging

logger = logging.getLogger(__name__)

def safe_edit_message(query, text, reply_markup=None):
    """Безопасное редактирование сообщения с игнорированием ошибки Message is not modified"""
    try:
        if reply_markup:
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            query.edit_message_text(text, parse_mode='Markdown')
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error editing message: {e}")

def safe_send_message(bot, chat_id, text, reply_markup=None, parse_mode='Markdown'):
    """Безопасная отправка сообщения с try/except"""
    try:
        if reply_markup:
            bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            bot.send_message(chat_id, text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")

import time
from database import get_cursor
from config import BUTTON_COOLDOWN, REQUEST_NUMBER_COOLDOWN

def check_cooldown(user_id, cooldown_type='button'):
    with get_cursor() as cur:
        cur.execute(f"SELECT last_{cooldown_type} FROM users WHERE id=%s", (user_id,))
        result = cur.fetchone()
        last = result[0] if result else 0
        now = int(time.time())
        
        cd = BUTTON_COOLDOWN if cooldown_type == 'button' else REQUEST_NUMBER_COOLDOWN
        
        if now - last < cd:
            return False, cd - (now - last)
        
        return True, 0

def update_cooldown(user_id, cooldown_type='button'):
    with get_cursor(commit=True) as cur:
        cur.execute(f"UPDATE users SET last_{cooldown_type}=%s WHERE id=%s", 
                   (int(time.time()), user_id))