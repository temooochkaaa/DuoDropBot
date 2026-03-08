import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor, reorder_queue
from keyboards import back, status_buttons
from config import MAX_RETRY_COUNT, EXTRA_REQUEST_COOLDOWN, MAX_ACTIVE_COLD
from states import WAITING_EXTRA
from utils.roles import get_role
from main import safe_edit_message, safe_send_message, check_cooldown, update_cooldown

logger = logging.getLogger(__name__)

def role_required(required_roles):
    def decorator(func):
        def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id
            role = get_role(user_id) or 'user'
            
            if role not in required_roles:
                if hasattr(update, 'callback_query') and update.callback_query:
                    update.callback_query.answer("❌ У вас нет прав для этого действия", show_alert=True)
                elif hasattr(update, 'message') and update.message:
                    safe_send_message(
                        context.bot, update.effective_chat.id,
                        "❌ У вас нет прав для этого действия."
                    )
                return None
            return func(update, context, *args, **kwargs)
        return wrapper
    return decorator

@role_required(['cold', 'helper', 'owner'])
def receive_photo(update, context):
    # Проверяем, что это фото
    if not update.message or not update.message.photo:
        safe_send_message(
            context.bot, update.effective_chat.id,
            "❌ Отправьте фото, а не файл."
        )
        return -1
    
    user_id = update.effective_user.id
    number_id = context.user_data.get('current_number')
    request_type = context.user_data.get('request_type')
    
    if not number_id:
        safe_send_message(
            context.bot, update.effective_chat.id,
            "❌ Ошибка: номер не найден."
        )
        return -1
    
    # Проверяем статус
    with get_cursor() as cur:
        cur.execute("SELECT taken_by, status FROM numbers WHERE id=%s", (number_id,))
        result = cur.fetchone()
        
        if not result or result[0] != user_id:
            safe_send_message(
                context.bot, update.effective_chat.id,
                "❌ Вы не можете отправить фото для этого номера."
            )
            return -1
        
        if result[1] != 'in_progress':
            safe_send_message(
                context.bot, update.effective_chat.id,
                "❌ Номер уже не в статусе ожидания кода."
            )
            return -1
    
    photo = update.message.photo[-1]
    photo_id = photo.file_id
    field = 'qr_photo_id' if request_type == 'qr' else 'code_photo_id'
    
    with get_cursor(commit=True) as cur:
        cur.execute(f"""
        UPDATE numbers 
        SET {field}=%s, code_sent_at=%s, status='code_sent'
        WHERE id=%s AND taken_by=%s
        RETURNING user_id, phone
        """, (photo_id, int(time.time()), number_id, user_id))
        
        result = cur.fetchone()
        
        if not result:
            safe_send_message(
                context.bot, update.effective_chat.id,
                "❌ Не удалось отправить фото."
            )
            return -1
        
        target_user, phone = result
        logger.info(f"Photo sent for number {number_id} to user {target_user}")
    
    caption = f"📷 Код для {phone}\n\nНажмите 'Код введен' после использования."
    
    try:
        context.bot.send_photo(
            chat_id=target_user,
            photo=photo_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Код введен", callback_data=f"code_entered_{number_id}")
            ]])
        )
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
    
    safe_send_message(
        context.bot, update.effective_chat.id,
        "✅ Код отправлен пользователю!",
        reply_markup=back("my_numbers")
    )
    
    # Очищаем временные данные
    context.user_data.pop('current_number', None)
    context.user_data.pop('request_type', None)
    return -1

def code_entered(update, context):
    query = update.callback_query
    query.answer()
    number_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    
    with get_cursor(commit=True) as cur:
        cur.execute("""
        UPDATE numbers 
        SET code_entered_at=%s, status='code_entered'
        WHERE id=%s AND user_id=%s AND status='code_sent'
        RETURNING taken_by, phone
        """, (int(time.time()), number_id, user_id))
        
        result = cur.fetchone()
        
        if not result:
            safe_edit_message(query, "❌ Номер не найден или не в статусе отправки кода.")
            return
        
        cold_id, phone = result
        logger.info(f"Code entered for number {number_id} by user {user_id}")
    
    if cold_id:
        safe_send_message(
            context.bot, cold_id,
            f"🔔 Пользователь подтвердил ввод кода для {phone}\n\nТеперь можно проверить активацию.",
            reply_markup=status_buttons(number_id)
        )
    
    safe_edit_message(query, "✅ Код подтвержден! Ожидайте активации.")

@role_required(['cold', 'helper', 'owner'])
def set_status(update, context):
    query = update.callback_query
    query.answer()
    
    data = query.data.split("_")
    status = data[0]  # activate, fail, crashed
    number_id = int(data[1])
    cold_id = query.from_user.id
    now = int(time.time())
    
    with get_cursor(commit=True) as cur:
        # Проверяем, что номер принадлежит этой холодке
        cur.execute("SELECT status, platform FROM numbers WHERE id=%s AND taken_by=%s", (number_id, cold_id))
        number = cur.fetchone()
        
        if not number:
            safe_edit_message(query, "❌ Номер не найден или вы не работаете с ним.")
            return
        
        current_status, platform = number
        
        # Проверяем допустимость перехода статуса
        valid_transitions = {
            'code_entered': ['activate', 'fail'],
            'activated': ['crashed'],
            'in_progress': ['activate', 'fail'],
            'code_sent': ['activate', 'fail']
        }
        
        if status not in valid_transitions.get(current_status, []):
            safe_edit_message(query, f"❌ Нельзя перейти из {current_status} в {status}.")
            return
        
        if status == 'activate':
            cur.execute("""
            UPDATE numbers SET activated_at=%s, status='activated' 
            WHERE id=%s AND taken_by=%s
            RETURNING user_id, phone
            """, (now, number_id, cold_id))
            
            result = cur.fetchone()
            if result:
                user_id, phone = result
                safe_send_message(context.bot, user_id, f"✅ Номер {phone} успешно активирован!")
                logger.info(f"Number {number_id} activated by cold {cold_id}")
                
        elif status == 'fail':
            cur.execute("""
            UPDATE numbers SET taken_by=NULL, status='failed' 
            WHERE id=%s AND taken_by=%s
            RETURNING user_id, phone
            """, (number_id, cold_id))
            
            result = cur.fetchone()
            if result:
                user_id, phone = result
                safe_send_message(
                    context.bot, user_id,
                    f"❌ Номер {phone} не удалось активировать.\nХотите попробовать снова?",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Повторить", callback_data=f"retry_number_{number_id}"),
                         InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_number_{number_id}")]
                    ])
                )
                reorder_queue(platform)
                logger.info(f"Number {number_id} failed by cold {cold_id}")
            
        elif status == 'crashed':
            cur.execute("""
            SELECT activated_at, user_id, phone FROM numbers WHERE id=%s
            """, (number_id,))
            activated, user_id, phone = cur.fetchone()
            
            work_time = now - activated if activated else 0
            
            cur.execute("""
            UPDATE numbers 
            SET crashed_at=%s, total_work_time=%s, status='crashed', taken_by=NULL
            WHERE id=%s AND taken_by=%s
            """, (now, work_time, number_id, cold_id))
            
            if cur.rowcount > 0:
                from utils.referrals import check_referral
                check_referral(user_id)
                
                hours = work_time // 3600
                minutes = (work_time % 3600) // 60
                safe_send_message(
                    context.bot, user_id,
                    f"💥 Номер {phone} слетел!\nПроработал: {hours}ч {minutes}мин"
                )
                reorder_queue(platform)
                logger.info(f"Number {number_id} crashed, worked {work_time}s")
    
    safe_edit_message(query, f"✅ Статус обновлен: {status}")
    
    # Очищаем временные данные
    context.user_data.pop('current_number', None)
    context.user_data.pop('request_type', None)

def retry_number(update, context):
    query = update.callback_query
    query.answer()
    number_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT retry_count, platform FROM numbers WHERE id=%s AND user_id=%s", (number_id, user_id))
        result = cur.fetchone()
        
        if not result:
            safe_edit_message(query, "❌ Номер не найден.")
            return
        
        retries, platform = result
        
        if retries >= MAX_RETRY_COUNT:
            cur.execute("UPDATE numbers SET status='failed', taken_by=NULL WHERE id=%s", (number_id,))
            safe_edit_message(
                query,
                f"❌ Превышен лимит попыток ({MAX_RETRY_COUNT}). Номер отклонён.",
                reply_markup=back("my_numbers")
            )
            reorder_queue(platform)
            logger.info(f"Number {number_id} exceeded retry limit")
            return
        
        cur.execute("""
        UPDATE numbers 
        SET status='waiting', taken_by=NULL, 
            code_photo_id=NULL, qr_photo_id=NULL,
            queue_position=NULL, retry_count=retry_count+1
        WHERE id=%s AND user_id=%s
        RETURNING retry_count
        """, (number_id, user_id))
        
        result = cur.fetchone()
        new_retries = result[0] if result else retries + 1
        reorder_queue(platform)
        logger.info(f"Number {number_id} retry {new_retries}/{MAX_RETRY_COUNT}")
    
    safe_edit_message(
        query,
        f"🔄 Номер возвращён в очередь (попытка {new_retries}/{MAX_RETRY_COUNT})",
        reply_markup=back("my_numbers")
    )

def cancel_number(update, context):
    query = update.callback_query
    query.answer()
    number_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT platform FROM numbers WHERE id=%s AND user_id=%s", (number_id, user_id))
        result = cur.fetchone()
        
        if result:
            platform = result[0]
            cur.execute("UPDATE numbers SET status='cancelled', in_queue=0, taken_by=NULL WHERE id=%s", (number_id,))
            reorder_queue(platform)
            logger.info(f"Number {number_id} cancelled by user {user_id}")
    
    safe_edit_message(query, "❌ Номер отменен.")

@role_required(['cold', 'helper', 'owner'])
def request_extra_info(update, context):
    query = update.callback_query
    query.answer()
    number_id = int(query.data.split("_")[2])
    cold_id = query.from_user.id
    now = int(time.time())
    
    with get_cursor() as cur:
        cur.execute("SELECT taken_by, last_extra_request FROM numbers WHERE id=%s", (number_id,))
        result = cur.fetchone()
        
        if not result or result[0] != cold_id:
            safe_edit_message(query, "❌ Вы не работаете с этим номером.")
            return
        
        last_extra = result[1] or 0
        if now - last_extra < EXTRA_REQUEST_COOLDOWN:
            wait = EXTRA_REQUEST_COOLDOWN - (now - last_extra)
            safe_edit_message(query, f"❌ Подождите {wait} сек перед следующим запросом.")
            return
    
    context.user_data['extra_number'] = number_id
    safe_edit_message(
        query,
        "📝 Введите дополнительную информацию для пользователя:",
        reply_markup=back("my_numbers")
    )
    return WAITING_EXTRA

@role_required(['cold', 'helper', 'owner'])
def receive_extra_info(update, context):
    extra_text = update.message.text
    cold_id = update.effective_user.id
    number_id = context.user_data.get('extra_number')
    
    if not number_id:
        safe_send_message(
            context.bot, update.effective_chat.id,
            "❌ Ошибка: номер не найден."
        )
        return -1
    
    with get_cursor(commit=True) as cur:
        cur.execute("""
        UPDATE numbers 
        SET waiting_for_extra=1, extra_request=%s, last_extra_request=%s
        WHERE id=%s AND taken_by=%s
        RETURNING user_id, phone
        """, (extra_text, int(time.time()), number_id, cold_id))
        
        result = cur.fetchone()
        
        if not result:
            safe_send_message(
                context.bot, update.effective_chat.id,
                "❌ Номер не найден."
            )
            return -1
        
        user_id, phone = result
        logger.info(f"Extra info requested for number {number_id}")
    
    safe_send_message(
        context.bot, user_id,
        f"📝 Холодка запрашивает дополнительную информацию для {phone}:\n\n{extra_text}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📝 Ответить", callback_data=f"reply_extra_{number_id}")
        ]])
    )
    
    safe_send_message(
        context.bot, update.effective_chat.id,
        "✅ Запрос отправлен пользователю!",
        reply_markup=back("my_numbers")
    )
    
    context.user_data.pop('extra_number', None)
    return -1

def process_extra_reply(update, context):
    query = update.callback_query
    query.answer()
    number_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    
    with get_cursor() as cur:
        cur.execute("SELECT user_id FROM numbers WHERE id=%s", (number_id,))
        result = cur.fetchone()
        
        if not result or result[0] != user_id:
            safe_edit_message(query, "❌ Это не ваш номер.")
            return
    
    context.user_data['reply_number'] = number_id
    safe_edit_message(query, "📝 Введите ваш ответ:")
    return WAITING_EXTRA

def save_extra_reply(update, context):
    reply_text = update.message.text
    user_id = update.effective_user.id
    number_id = context.user_data.get('reply_number')
    
    if not number_id:
        safe_send_message(
            context.bot, update.effective_chat.id,
            "❌ Ошибка: номер не найден."
        )
        return -1
    
    with get_cursor() as cur:
        cur.execute("SELECT taken_by FROM numbers WHERE id=%s", (number_id,))
        result = cur.fetchone()
        
        if result and result[0]:
            cold_id = result[0]
            safe_send_message(
                context.bot, cold_id,
                f"📝 Получен ответ на доп запрос для номера:\n\n{reply_text}"
            )
            safe_send_message(
                context.bot, update.effective_chat.id,
                "✅ Ответ отправлен холодке!"
            )
            logger.info(f"Extra reply sent for number {number_id}")
        else:
            safe_send_message(
                context.bot, update.effective_chat.id,
                "❌ Холодка не найдена."
            )
    
    from keyboards import main_menu
    from utils.roles import get_role
    role = get_role(user_id) or 'user'
    safe_send_message(
        context.bot, update.effective_chat.id,
        "Главное меню:",
        reply_markup=main_menu(role)
    )
    
    context.user_data.pop('reply_number', None)
    return -1