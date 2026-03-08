import tempfile
import os
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor
from keyboards import helper_panel_menu, back
from utils.stats import generate_daily_stats
from config import ALL_NUMBERS_PER_PAGE
from utils.helpers import safe_edit_message, safe_send_message  # Вместо from main import ...

def helper_panel(update, context):
    query = update.callback_query
    query.answer()
    safe_edit_message(
        query,
        "👥 **Панель помощника**\n\nВыберите действие:",
        reply_markup=helper_panel_menu()
    )

def stats_whatsapp(update, context):
    query = update.callback_query
    query.answer()
    stats = generate_daily_stats('whatsapp')
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(stats)
        tmp_path = f.name
    
    try:
        with open(tmp_path, 'rb') as f:
            context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=f"whatsapp_stats_{int(time.time())}.txt",
                caption="📊 Статистика WhatsApp за сегодня"
            )
    except Exception as e:
        logger.error(f"Error sending stats: {e}")
    
    time.sleep(1)
    try:
        os.unlink(tmp_path)
    except:
        pass
    
    safe_send_message(
        context.bot, query.from_user.id,
        "📊 Статистика отправлена.",
        reply_markup=back("helper_panel")
    )

def stats_max(update, context):
    query = update.callback_query
    query.answer()
    stats = generate_daily_stats('max')
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(stats)
        tmp_path = f.name
    
    try:
        with open(tmp_path, 'rb') as f:
            context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=f"max_stats_{int(time.time())}.txt",
                caption="📊 Статистика MAX за сегодня"
            )
    except Exception as e:
        logger.error(f"Error sending stats: {e}")
    
    time.sleep(1)
    try:
        os.unlink(tmp_path)
    except:
        pass
    
    safe_send_message(
        context.bot, query.from_user.id,
        "📊 Статистика отправлена.",
        reply_markup=back("helper_panel")
    )

def all_numbers(update, context):
    query = update.callback_query
    query.answer()
    page = context.user_data.get('all_numbers_page', 0)
    offset = page * ALL_NUMBERS_PER_PAGE
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT id, phone, platform, status, taken_by, queue_position 
        FROM numbers 
        WHERE in_queue=1
        ORDER BY queue_position
        LIMIT %s OFFSET %s
        """, (ALL_NUMBERS_PER_PAGE, offset))
        
        rows = cur.fetchall()
        
        cur.execute("SELECT COUNT(*) FROM numbers WHERE in_queue=1")
        total = cur.fetchone()[0]
    
    if not rows:
        safe_edit_message(
            query,
            "📭 Нет номеров в очереди.",
            reply_markup=back("helper_panel")
        )
        return
    
    total_pages = (total - 1) // ALL_NUMBERS_PER_PAGE + 1
    
    if page < 0:
        page = 0
    if page >= total_pages and total_pages > 0:
        page = total_pages - 1
    
    text = f"📋 **Все номера** (страница {page+1}/{total_pages}):\n\n"
    for i, r in enumerate(rows, 1):
        taken = f"👤 {r[4]}" if r[4] else "🆓 свободен"
        emoji = "📱" if r[2] == 'whatsapp' else "📲"
        text += f"{i}. {emoji} #{r[0]} {r[1]} - {r[3]} {taken} (поз.{r[5]})\n"
    
    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data="all_prev"))
    if offset + ALL_NUMBERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("➡️ Вперед", callback_data="all_next"))
    
    if nav:
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton("🔙 В меню", callback_data="helper_panel")])
    
    context.user_data['all_page'] = page
    
    safe_edit_message(
        query,
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def all_pagination(update, context):
    query = update.callback_query
    query.answer()
    direction = query.data.split('_')[1]
    
    page = context.user_data.get('all_page', 0)
    if direction == 'prev':
        page = max(0, page - 1)
    else:
        page += 1
    
    context.user_data['all_page'] = page
    all_numbers(update, context)

def remove_number_start(update, context):
    query = update.callback_query
    query.answer()
    safe_edit_message(
        query,
        "🗑 Введите ID номера для удаления:",
        reply_markup=back("helper_panel")
    )
    from states import WAITING_REMOVE_ID
    return WAITING_REMOVE_ID

def remove_number_process(update, context):
    if not update.message:
        return -1
        
    try:
        number_id = int(update.message.text.strip())
    except:
        safe_send_message(
            context.bot, update.effective_chat.id,
            "❌ Неверный ID. Введите число.",
            reply_markup=back("helper_panel")
        )
        return -1
    
    with get_cursor(commit=True) as cur:
        cur.execute("""
        UPDATE numbers SET status='cancelled', in_queue=0, taken_by=NULL 
        WHERE id=%s
        RETURNING platform
        """, (number_id,))
        
        result = cur.fetchone()
        
        if result:
            platform = result[0]
            from database import reorder_queue
            reorder_queue(platform)
            safe_send_message(
                context.bot, update.effective_chat.id,
                f"✅ Номер #{number_id} удален из очереди.",
                reply_markup=back("helper_panel")
            )
            logger.info(f"Number {number_id} removed by helper")
        else:
            safe_send_message(
                context.bot, update.effective_chat.id,
                f"❌ Номер #{number_id} не найден.",
                reply_markup=back("helper_panel")
            )
    
    return -1