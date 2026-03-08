import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor, reorder_queue
from keyboards import back, queue_menu, number_detail_menu, main_menu
from datetime import datetime
from config import TIMEZONE
from utils.helpers import safe_edit_message, safe_send_message
from utils.roles import get_role

logger = logging.getLogger(__name__)

def check_queue(update, context):
    """Главное меню очереди"""
    query = update.callback_query
    query.answer()
    safe_edit_message(
        query,
        "📊 Выберите очередь:",
        reply_markup=queue_menu()
    )

def show_queue(update, context):
    """Показать очередь для конкретной платформы"""
    query = update.callback_query
    query.answer()
    
    platform = query.data.split("_")[2]  # whatsapp или max
    user_id = query.from_user.id
    
    with get_cursor() as cur:
        # Используем ROW_NUMBER для отображения порядкового номера
        cur.execute("""
        SELECT id, phone, queue_position, created_at,
               ROW_NUMBER() OVER (ORDER BY queue_position) as row_num
        FROM numbers 
        WHERE user_id=%s AND platform=%s AND status='waiting' AND in_queue=1
        ORDER BY queue_position
        """, (user_id, platform))
        
        rows = cur.fetchall()
    
    if not rows:
        safe_edit_message(
            query,
            f"📭 У вас нет номеров в очереди {platform.upper()}.",
            reply_markup=back("check_queue")
        )
        return
    
    text = f"📊 **Очередь {platform.upper()}:**\n\n"
    buttons = []
    
    for r in rows:
        number_id, phone, position, created, row_num = r
        created_time = datetime.fromtimestamp(created, TIMEZONE).strftime('%d.%m %H:%M')
        text += f"{row_num}. 📞 {phone} - позиция {position} (с {created_time})\n"
        buttons.append([
            InlineKeyboardButton(f"📞 {phone}", callback_data=f"queue_detail_{number_id}")
        ])
    
    buttons.append([InlineKeyboardButton("⬅ Назад", callback_data="check_queue")])
    
    safe_edit_message(
        query,
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def queue_detail(update, context):
    """Детальная информация о номере в очереди"""
    query = update.callback_query
    query.answer()
    
    number_id = int(query.data.split("_")[2])
    user_id = query.from_user.id
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT phone, platform, queue_position, created_at FROM numbers 
        WHERE id=%s AND user_id=%s
        """, (number_id, user_id))
        
        result = cur.fetchone()
        
        if not result:
            safe_edit_message(query, "❌ Номер не найден.")
            return
        
        phone, platform, position, created = result
        created_time = datetime.fromtimestamp(created, TIMEZONE).strftime('%d.%m.%Y %H:%M:%S')
        
        text = (
            f"📞 **Номер:** {phone}\n"
            f"📱 **Платформа:** {platform.upper()}\n"
            f"🔢 **Позиция в очереди:** {position}\n"
            f"📅 **Поставлен:** {created_time}\n\n"
            f"Удалить номер из очереди?"
        )
        
        safe_edit_message(
            query,
            text,
            reply_markup=number_detail_menu(number_id)
        )

def delete_from_queue(update, context):
    """Удалить номер из очереди"""
    query = update.callback_query
    query.answer()
    
    logger.info(f"Delete function called by user {query.from_user.id}")
    
    try:
        # Парсим ID номера
        parts = query.data.split("_")
        logger.info(f"Callback data parts: {parts}")
        
        if len(parts) < 3:
            logger.error(f"Invalid callback data: {query.data}")
            query.edit_message_text("❌ Ошибка: неверный формат данных.")
            return
        
        number_id = int(parts[2])
        user_id = query.from_user.id
        logger.info(f"Attempting to delete number {number_id} for user {user_id}")
        
        with get_cursor(commit=True) as cur:
            # Проверяем, существует ли номер и принадлежит ли пользователю
            cur.execute("""
            SELECT id, platform FROM numbers 
            WHERE id=%s AND user_id=%s AND status='waiting'
            """, (number_id, user_id))
            
            result = cur.fetchone()
            logger.info(f"Number check result: {result}")
            
            if not result:
                logger.warning(f"Number {number_id} not found or not in waiting status")
                query.edit_message_text("❌ Номер не найден или уже не в очереди.")
                return
            
            platform = result[1]
            
            # Удаляем номер
            cur.execute("""
            UPDATE numbers SET status='cancelled', in_queue=0, taken_by=NULL 
            WHERE id=%s AND user_id=%s AND status='waiting'
            """, (number_id, user_id))
            
            deleted = cur.rowcount
            logger.info(f"Deleted rows: {deleted}")
            
            if deleted > 0:
                # Пересчитываем очередь
                from database import reorder_queue
                reorder_queue(platform)
                logger.info(f"Number {number_id} deleted from queue by user {user_id}")
                
                # Удаляем старое сообщение и отправляем новое
                query.message.delete()
                
                # Возвращаемся в главное меню
                role = get_role(user_id) or 'user'
                context.bot.send_message(
                    chat_id=user_id,
                    text="✅ Номер успешно удален из очереди.\n\nГлавное меню:",
                    reply_markup=main_menu(role)
                )
            else:
                logger.warning(f"No rows deleted for number {number_id}")
                query.edit_message_text("❌ Не удалось удалить номер.")
                
    except ValueError as e:
        logger.error(f"Value error parsing number ID: {e}")
        query.edit_message_text("❌ Ошибка: неверный ID номера.")
    except Exception as e:
        logger.error(f"Unexpected error deleting number: {e}", exc_info=True)
        query.edit_message_text("❌ Произошла внутренняя ошибка.")