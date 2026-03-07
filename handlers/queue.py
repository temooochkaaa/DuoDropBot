from database import get_cursor
from keyboards import back

def check_queue(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT phone, platform, queue_position FROM numbers 
        WHERE user_id=%s AND status='waiting' AND in_queue=1
        ORDER BY queue_position
        """, (user_id,))
        
        rows = cur.fetchall()
    
    if not rows:
        query.edit_message_text(
            "📭 У вас нет номеров в очереди.",
            reply_markup=back("menu")
        )
        return
    
    text = "📊 **Ваша очередь:**\n\n"
    for r in rows:
        emoji = "📱" if r[1] == 'whatsapp' else "📲"
        text += f"{emoji} {r[0]} - позиция {r[2]}\n"
    
    query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=back("menu")
    )