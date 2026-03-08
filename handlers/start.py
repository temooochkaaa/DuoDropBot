import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor
from keyboards import main_menu
from config import OWNER_ID
from main import safe_edit_message, safe_send_message

AGREEMENT_TEXT = """
📋 **ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ**

1. Все действия с аккаунтами производятся добровольно.
2. Администрация не несет ответственности за последствия.
3. Запрещено использовать бота для противоправных действий.

Нажимая «Принять», вы соглашаетесь с условиями.
"""

def start(update, context):
    user = update.effective_user
    
    # Реферальная система
    ref = None
    if context.args:
        try:
            ref = int(context.args[0])
            if ref != user.id:  # Нельзя реферить самого себя
                with get_cursor(commit=True) as cur:
                    cur.execute("""
                    INSERT INTO referrals (referrer_id, referred_id, status)
                    VALUES (%s, %s, 'pending')
                    ON CONFLICT (referrer_id, referred_id) DO NOTHING
                    """, (ref, user.id))
                    if cur.rowcount > 0:
                        logger.info(f"Referral link clicked: {ref} -> {user.id}")
        except:
            pass
    
    role = "user"
    if user.id == OWNER_ID:
        role = "owner"
    
    with get_cursor(commit=True) as cur:
        cur.execute("""
        INSERT INTO users (id, username, first_name, role, referred_by, created_at, last_button_click, last_request)
        VALUES (%s, %s, %s, %s, %s, %s, 0, 0)
        ON CONFLICT (id) DO NOTHING
        """, (user.id, user.username, user.first_name, role, ref, int(time.time())))
    
    with get_cursor() as cur:
        cur.execute("SELECT accepted FROM users WHERE id=%s", (user.id,))
        result = cur.fetchone()
        accepted = result[0] if result else 0
    
    if not accepted:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Принять", callback_data="accept_agreement")]
        ])
        
        safe_send_message(
            context.bot, update.effective_chat.id,
            AGREEMENT_TEXT,
            reply_markup=keyboard
        )
        return
    
    safe_send_message(
        context.bot, update.effective_chat.id,
        "👋 Добро пожаловать в DuoDropTeam!\n\nВыберите действие:",
        reply_markup=main_menu(role)
    )

def accept_agreement(update, context):
    query = update.callback_query
    query.answer()
    
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET accepted=1 WHERE id=%s", (query.from_user.id,))
    
    from utils.roles import get_role
    role = get_role(query.from_user.id) or 'user'
    
    safe_edit_message(
        query,
        "✅ Соглашение принято!",
        reply_markup=main_menu(role)
    )