import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor, reorder_queue
from keyboards import cold_panel_menu, back, number_actions_menu
from config import GROUP_ID, NUMBERS_PER_PAGE

def cold_panel(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "❄️ Панель холодки",
        reply_markup=cold_panel_menu()
    )

def request_number(update, context):
    query = update.callback_query
    query.answer()
    platform = query.data.split("_")[1]
    
    context.bot.send_message(
        GROUP_ID,
        f"🆕 Требуется номер {platform.upper()}!\nНажмите 'Сдать номер' в боте."
    )
    
    query.edit_message_text(
        "✅ Запрос отправлен в группу!",
        reply_markup=back("cold_panel")
    )

def free_numbers(update, context):
    query = update.callback_query
    query.answer()
    
    page = context.user_data.get('numbers_page', 0)
    offset = page * NUMBERS_PER_PAGE
    platform = context.user_data.get('current_platform', 'whatsapp')
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT id, phone FROM numbers 
        WHERE platform=%s AND status='waiting' AND taken_by IS NULL AND in_queue=1
        ORDER BY queue_position
        LIMIT %s OFFSET %s
        """, (platform, NUMBERS_PER_PAGE, offset))
        
        rows = cur.fetchall()
        
        cur.execute("""
        SELECT COUNT(*) FROM numbers 
        WHERE platform=%s AND status='waiting' AND taken_by IS NULL AND in_queue=1
        """, (platform,))
        total = cur.fetchone()[0]
    
    if not rows:
        query.edit_message_text(
            f"📭 Нет свободных номеров {platform.upper()}.",
            reply_markup=back("cold_panel")
        )
        return
    
    total_pages = (total - 1) // NUMBERS_PER_PAGE + 1
    
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    buttons = []
    for r in rows:
        emoji = "📱" if platform == 'whatsapp' else "📲"
        buttons.append([
            InlineKeyboardButton(
                f"{emoji} {r[1]}",
                callback_data=f"view_number_{r[0]}"
            )
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="numbers_prev"))
    if offset + NUMBERS_PER_PAGE < total:
        nav_buttons.append(InlineKeyboardButton("➡️ Вперед", callback_data="numbers_next"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔙 В меню", callback_data="cold_panel")])
    
    context.user_data['numbers_page'] = page
    context.user_data['current_platform'] = platform
    
    query.edit_message_text(
        f"📋 Свободные номера {platform.upper()} (страница {page+1}/{total_pages}):",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def numbers_pagination(update, context):
    query = update.callback_query
    query.answer()
    direction = query.data.split('_')[1]
    
    page = context.user_data.get('numbers_page', 0)
    page = page - 1 if direction == 'prev' else page + 1
    context.user_data['numbers_page'] = page
    
    free_numbers(update, context)

def view_number(update, context):
    query = update.callback_query
    query.answer()
    number_id = int(query.data.split("_")[2])
    
    with get_cursor() as cur:
        cur.execute("SELECT phone, platform, taken_by FROM numbers WHERE id=%s", (number_id,))
        result = cur.fetchone()
        
        if not result:
            query.edit_message_text("❌ Номер не найден.")
            return
        
        phone, platform, taken = result
    
    context.user_data['current_number'] = number_id
    context.user_data['current_platform'] = platform
    
    text = f"📞 Номер: {phone}\nПлатформа: {platform.upper()}"
    if taken:
        text += f"\n👤 Взял: {taken}"
    
    query.edit_message_text(
        text,
        reply_markup=number_actions_menu(number_id, platform, taken is not None)
    )

def take_number(update, context):
    query = update.callback_query
    query.answer()
    cold_id = query.from_user.id
    data = query.data.split("_")
    
    action = data[1]  # code, qr, или max
    number_id = int(data[2])
    
    # Атомарная операция взятия номера
    with get_cursor(commit=True) as cur:
        cur.execute("""
        UPDATE numbers 
        SET taken_by=%s, status='in_progress'
        WHERE id=%s AND taken_by IS NULL
        RETURNING id, platform, phone
        """, (cold_id, number_id))
        
        result = cur.fetchone()
        
        if not result:
            query.edit_message_text(
                "❌ Этот номер уже взят другим.",
                reply_markup=back("free_numbers")
            )
            return
        
        number_id, platform, phone = result
    
    # Пересчитываем очередь после взятия
    reorder_queue(platform)
    
    request_type = action if action in ['code', 'qr'] else None
    
    context.user_data['current_number'] = number_id
    context.user_data['request_type'] = request_type
    context.user_data['current_platform'] = platform
    
    if platform == 'whatsapp':
        query.edit_message_text(
            f"📷 Номер {phone} взят. Отправьте фото с кодом или QR:",
            reply_markup=back("free_numbers")
        )
        from states import WAITING_PHOTO
        return WAITING_PHOTO
    else:
        query.edit_message_text(
            f"✅ Номер {phone} взят. Используйте кнопки для действий.",
            reply_markup=number_actions_menu(number_id, platform, True)
        )