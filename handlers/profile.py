import tempfile
import os
import time
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor
from keyboards import back
from utils.referrals import get_referral_info
from utils.roles import get_role
from utils.stats import generate_user_stats
from config import GROUP_LINK, REPUTATION_LINK

def profile(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT username, first_name, role, created_at FROM users WHERE id=%s
        """, (user_id,))
        user = cur.fetchone()
    
    if not user:
        query.edit_message_text("❌ Пользователь не найден.")
        return
    
    ref_info = get_referral_info(user_id)
    ref_count = ref_info[0] if ref_info else 0
    ref_balance = ref_info[1] if ref_info else 0
    
    joined = datetime.fromtimestamp(user[3]).strftime('%d.%m.%Y') if user[3] else 'неизвестно'
    
    text = (
        f"👤 **Профиль пользователя**\n\n"
        f"**ID:** `{user_id}`\n"
        f"**Username:** @{user[0] or 'нет'}\n"
        f"**Имя:** {user[1]}\n"
        f"**Роль:** {user[2]}\n"
        f"**Дата регистрации:** {joined}\n\n"
        f"💰 **Рефералы:** {ref_count}\n"
        f"💵 **Баланс:** ${ref_balance:.2f}\n\n"
        f"📢 **Наша группа:** [ссылка]({GROUP_LINK})\n"
        f"⭐ **Репутация:** [ссылка]({REPUTATION_LINK})"
    )
    
    buttons = [
        [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton("⬅ Назад", callback_data="menu")]
    ]
    
    query.edit_message_text(
        text,
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def my_stats(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    stats_text = generate_user_stats(user_id)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(stats_text)
        tmp_path = f.name
    
    with open(tmp_path, 'rb') as f:
        context.bot.send_document(
            chat_id=user_id,
            document=f,
            filename=f"stats_{user_id}_{int(time.time())}.txt",
            caption="📊 Ваша статистика"
        )
    
    time.sleep(1)
    try:
        os.unlink(tmp_path)
    except:
        pass
    
    query.message.reply_text(
        "📊 Статистика отправлена.",
        reply_markup=back("profile")
    )