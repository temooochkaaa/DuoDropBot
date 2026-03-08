import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor, reorder_queue
from keyboards import cold_panel_menu, back, number_actions_menu
from config import GROUP_ID, NUMBERS_PER_PAGE, MAX_ACTIVE_COLD
from utils.helpers import safe_edit_message, safe_send_message 
from utils.helpers import check_cooldown, update_cooldown

def cold_panel(update, context):
    query = update.callback_query
    query.answer()
    safe_edit_message(
        query,
        "❄️ Панель холодки",
        reply_markup=cold_panel_menu()
    )

def request_number(update, context):
    query = update.callback_query
    query.answer()
    cold_id = query.from_user.id
    
    # Проверяем кулдаун
    ok, wait = check_cooldown(cold_id, 'request')
    if not ok:
        safe_edit_message(
            query,
            f"❌ Подождите {wait} сек перед следующим запросом.",
            reply_markup=back("cold_panel")
        )
        return
    
    platform = query.data.split("_")[2]  # whatsapp или max
    
    safe_send_message(
        context.bot, GROUP_ID,
        f"🆕 Требуется номер {platform.upper()}!\nНажмите 'Сдать номер' в боте."
    )
    
    update_cooldown(cold_id, 'request')
    
    safe_edit_message(
        query,
        "✅ Запрос отправлен в группу!",
        reply_markup=back("cold_panel")
    )

def free_numbers(update, context):
    query = update.callback_query
    query.answer()
    
    # Получаем платформу из callback_data
    platform = query.data.split("_")[2]  # whatsapp или max
    page_key = f'numbers_page_{platform}'
    page = context.user_data.get(page_key, 0)
    offset = page * NUMBERS_PER_PAGE
    
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
        safe_edit_message(
            query,
            f"📭 Нет свободных номеров {platform.upper()}.",
            reply_markup=back("cold_panel")
        )
        return
    
    total_pages = (total - 1) // NUMBERS_PER_PAGE + 1
    
    # Защита от выхода за пределы
    if page < 0:
        page = 0
    if page >= total_pages and total_pages > 0:
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
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"numbers_prev_{platform}"))
    if offset + NUMBERS_PER_PAGE < total:
        nav_buttons.append(InlineKeyboardButton("➡️ Вперед", callback_data=f"numbers_next_{platform}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔙 В меню", callback_data="cold_panel")])
    
    # Сохраняем данные
    context.user_data[page_key] = page
    context.user_data['current_platform'] = platform
    
    safe_edit_message(
        query,
        f"📋 Свободные номера {platform.upper()} (страница {page+1}/{total_pages}):",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def numbers_pagination(update, context):
    query = update.callback_query
    query.answer()
    
    parts = query.data.split("_")
    direction = parts[1]  # prev или next
    platform = parts[2]   # whatsapp или max
    
    page_key = f'numbers_page_{platform}'
    page = context.user_data.get(page_key, 0)
    
    if direction == 'prev':
        page = max(0, page - 1)
    else:
        page += 1
    
    context.user_data[page_key] = page
    context.user_data['current_platform'] = platform
    
    # Перезагружаем список
    query.data = f"free_numbers_{platform}"
    free_numbers(update, context)

def view_number(update, context):
    query = update.callback_query
    query.answer()
    number_id = int(query.data.split("_")[2])
    
    with get_cursor() as cur:
        cur.execute("SELECT phone, platform, taken_by FROM numbers WHERE id=%s", (number_id,))
        result = cur.fetchone()
        
        if not result:
            safe_edit_message(query, "❌ Номер не найден.")
            return
        
        phone, platform, taken = result
    
    context.user_data['current_number'] = number_id
    context.user_data['current_platform'] = platform
    
    text = f"📞 Номер: {phone}\nПлатформа: {platform.upper()}"
    if taken:
        text += f"\n👤 Взял: {taken}"
    
    safe_edit_message(
        query,
        text,
        reply_markup=number_actions_menu(number_id, platform, taken is not None)
    )

def take_number(update, context):
    query = update.callback_query
    query.answer()
    cold_id = query.from_user.id
    number_id = int(query.data.split("_")[2])
    
    # Проверяем кулдаун
    ok, wait = check_cooldown(cold_id, 'button')
    if not ok:
        query.answer(f"⏳ Подождите {wait} сек", show_alert=True)
        return
    
    # Проверяем лимит активных номеров у холодки
    with get_cursor() as cur:
        cur.execute("""
        SELECT COUNT(*) FROM numbers 
        WHERE taken_by=%s AND status IN ('in_progress', 'code_sent', 'code_entered')
        """, (cold_id,))
        active_count = cur.fetchone()[0]
        
        if active_count >= MAX_ACTIVE_COLD:
            safe_edit_message(
                query,
                f"❌ У вас уже {MAX_ACTIVE_COLD} активных номеров.",
                reply_markup=back("cold_panel")
            )
            return
    
    # Получаем платформу из базы
    with get_cursor() as cur:
        cur.execute("SELECT platform FROM numbers WHERE id=%s", (number_id,))
        result = cur.fetchone()
        if not result:
            safe_edit_message(query, "❌ Номер не найден.")
            return
        platform = result[0]
    
    # Атомарная операция взятия номера
    with get_cursor(commit=True) as cur:
        cur.execute("""
        UPDATE numbers 
        SET taken_by=%s, status='in_progress'
        WHERE id=%s AND taken_by IS NULL AND status='waiting'
        RETURNING id, phone
        """, (cold_id, number_id))
        
        result = cur.fetchone()
        
        if not result:
            safe_edit_message(
                query,
                "❌ Этот номер уже взят другим.",
                reply_markup=back("cold_panel")
            )
            return
        
        number_id, phone = result
        logger.info(f"Number {number_id} taken by cold {cold_id}")
    
    update_cooldown(cold_id, 'button')
    
    # Пересчитываем очередь после взятия
    reorder_queue(platform)
    
    context.user_data['current_number'] = number_id
    context.user_data['request_type'] = query.data.split("_")[1]  # code, qr, max
    context.user_data['current_platform'] = platform
    
    if platform == 'whatsapp':
        safe_edit_message(
            query,
            f"📷 Номер {phone} взят. Отправьте фото с кодом или QR:",
            reply_markup=back("cold_panel")
        )
        from states import WAITING_PHOTO
        return WAITING_PHOTO
    else:
        safe_edit_message(
            query,
            f"✅ Номер {phone} взят. Используйте кнопки для действий.",
            reply_markup=number_actions_menu(number_id, platform, True)
        )