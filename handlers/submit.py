import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor, reorder_queue
from keyboards import submit_menu, back
from utils.validators import validate_phone, check_duplicate, can_submit_again
from utils.referrals import check_referral
from utils.db_helpers import get_queue_count
from config import MAX_ACTIVE_NUMBERS
from states import WAITING_NUMBER_WHATSAPP, WAITING_NUMBER_MAX
from main import safe_edit_message, safe_send_message

def submit_menu_handler(update, context):
    query = update.callback_query
    query.answer()
    safe_edit_message(
        query,
        "📱 Выберите платформу:",
        reply_markup=submit_menu()
    )

def submit_whatsapp(update, context):
    query = update.callback_query
    query.answer()
    safe_edit_message(
        query,
        "📞 Введите номер для WhatsApp (только цифры, 10-15 цифр, например: 79123456789):",
        reply_markup=back()
    )
    return WAITING_NUMBER_WHATSAPP

def submit_max(update, context):
    query = update.callback_query
    query.answer()
    safe_edit_message(
        query,
        "📞 Введите номер для MAX (только цифры, 10-15 цифр, например: 79123456789):",
        reply_markup=back()
    )
    return WAITING_NUMBER_MAX

def process_whatsapp_number(update, context):
    return process_number(update, context, 'whatsapp', WAITING_NUMBER_WHATSAPP)

def process_max_number(update, context):
    return process_number(update, context, 'max', WAITING_NUMBER_MAX)

def process_number(update, context, platform, state):
    if not update.message:
        return -1
        
    phone = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not validate_phone(phone):
        safe_send_message(
            context.bot, update.effective_chat.id,
            "❌ Неверный формат. Введите 10-15 цифр.",
            reply_markup=back()
        )
        return state
    
    duplicate = check_duplicate(user_id, phone, platform)
    if duplicate:
        status = duplicate[1]
        if not can_submit_again(status):
            status_text = {
                'waiting': 'ожидает в очереди',
                'in_progress': 'в работе',
                'activated': 'активирован'
            }.get(status, 'активен')
            safe_send_message(
                context.bot, update.effective_chat.id,
                f"❌ Этот номер уже {status_text}.",
                reply_markup=back()
            )
            return state
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT COUNT(*) FROM numbers 
        WHERE user_id=%s AND status IN ('waiting', 'in_progress')
        """, (user_id,))
        active_count = cur.fetchone()[0]
        
        if active_count >= MAX_ACTIVE_NUMBERS:
            safe_send_message(
                context.bot, update.effective_chat.id,
                f"❌ Превышен лимит активных номеров ({MAX_ACTIVE_NUMBERS}).",
                reply_markup=back()
            )
            return state
    
    queue_pos = get_queue_count(platform) + 1
    
    with get_cursor(commit=True) as cur:
        cur.execute("""
        INSERT INTO numbers (user_id, phone, platform, status, queue_position, created_at)
        VALUES (%s, %s, %s, 'waiting', %s, %s)
        RETURNING id
        """, (user_id, phone, platform, queue_pos, int(time.time())))
        number_id = cur.fetchone()[0]
        
        logger.info(f"Number added: {phone} ({platform}) by user {user_id}, pos {queue_pos}")
    
    check_referral(user_id)
    
    from keyboards import main_menu
    from utils.roles import get_role
    
    safe_send_message(
        context.bot, update.effective_chat.id,
        f"✅ Номер принят! Ваша позиция: {queue_pos}",
        reply_markup=main_menu(get_role(user_id))
    )
    
    context.user_data.clear()
    return -1