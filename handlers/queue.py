from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor, reorder_queue
from keyboards import back, queue_menu, number_detail_menu
from datetime import datetime
from config import TIMEZONE
from utils.helpers import safe_edit_message, safe_send_message  # Вместо from main import ...

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
    
    try:
        number_id = int(query.data.split("_")[2])
        user_id = query.from_user.id
        
        with get_cursor(commit=True) as cur:
            cur.execute("""
            UPDATE numbers SET status='cancelled', in_queue=0, taken_by=NULL 
            WHERE id=%s AND user_id=%s AND status='waiting'
            RETURNING platform
            """, (number_id, user_id))
            
            result = cur.fetchone()
            
            if result:
                platform = result[0]
                from database import reorder_queue
                reorder_queue(platform)
                logger.info(f"Number {number_id} deleted from queue by user {user_id}")
                
                # Показываем сообщение об успехе
                query.edit_message_text("✅ Номер успешно удален из очереди.")
                
                # Возвращаемся к списку очереди через 2 секунды
                import time
                time.sleep(2)
                show_queue(update, context)
            else:
                query.edit_message_text("❌ Номер не найден или уже не в очереди.")
    except Exception as e:
        logger.error(f"Error deleting number: {e}")
        query.edit_message_text("❌ Произошла ошибка при удалении.")