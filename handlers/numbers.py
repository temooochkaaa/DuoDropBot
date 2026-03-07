from database import get_cursor
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from keyboards import back

def my_numbers(update, context):
    query = update.callback_query
    query.answer()
    cold_id = query.from_user.id
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT id, phone, platform, status FROM numbers 
        WHERE taken_by=%s AND status NOT IN ('activated', 'crashed', 'failed', 'cancelled')
        ORDER BY created_at DESC
        """, (cold_id,))
        
        rows = cur.fetchall()
    
    if not rows:
        query.edit_message_text(
            "📭 У вас нет активных номеров.",
            reply_markup=back("cold_panel")
        )
        return
    
    buttons = []
    for r in rows:
        emoji = "📱" if r[2] == 'whatsapp' else "📲"
        buttons.append([
            InlineKeyboardButton(
                f"{emoji} {r[1]} ({r[3]})",
                callback_data=f"view_number_{r[0]}"
            )
        ])
    
    buttons.append([InlineKeyboardButton("🔙 В меню", callback_data="cold_panel")])
    
    query.edit_message_text(
        "📋 Ваши активные номера:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )