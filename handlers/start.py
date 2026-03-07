import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor
from keyboards import main_menu
from config import OWNER_ID

AGREEMENT_TEXT = """
📋 **ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ**

1. Все действия с аккаунтами производятся добровольно.
2. Администрация не несет ответственности за последствия.
3. Запрещено использовать бота для противоправных действий.

Нажимая «Принять», вы соглашаетесь с условиями.
"""

def start(update, context):
    user = update.effective_user
    
    ref = None
    if context.args:
        try:
            ref = int(context.args[0])
        except:
            pass
    
    role = "user"
    if user.id == OWNER_ID:
        role = "owner"
    
    with get_cursor(commit=True) as cur:
        cur.execute("""
        INSERT INTO users (id, username, first_name, role, referred_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """, (user.id, user.username, user.first_name, role, ref, int(time.time())))
    
    with get_cursor() as cur:
        cur.execute("SELECT accepted FROM users WHERE id=%s", (user.id,))
        result = cur.fetchone()
        accepted = result[0] if result else 0
    
    if not accepted:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Принять", callback_data="accept")],
            [InlineKeyboardButton("❌ Отказаться", callback_data="decline")]
        ])
        
        update.message.reply_text(
            AGREEMENT_TEXT,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        return
    
    update.message.reply_text(
        "👋 Добро пожаловать в DuoDropTeam!\n\nВыберите действие:",
        reply_markup=main_menu(role)
    )

def accept_agreement(update, context):
    query = update.callback_query
    query.answer()
    
    if query.data == "decline":
        query.edit_message_text("❌ До свидания!")
        return
    
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET accepted=1 WHERE id=%s", (query.from_user.id,))
    
    from utils.roles import get_role
    role = get_role(query.from_user.id) or 'user'
    
    query.edit_message_text(
        "✅ Соглашение принято!",
        reply_markup=main_menu(role)
    )