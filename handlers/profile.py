import tempfile
import os
import time
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor
from keyboards import back, profile_menu
from utils.referrals import get_referral_info
from utils.roles import get_role
from utils.stats import generate_user_stats
from config import GROUP_LINK, REPUTATION_LINK, SUPPORT
from utils.helpers import safe_edit_message, safe_send_message  # Вместо from main import ...

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
        safe_edit_message(query, "❌ Пользователь не найден.")
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
    
    safe_edit_message(
        query,
        text,
        reply_markup=profile_menu()
    )

def my_stats(update, context):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    stats_text = generate_user_stats(user_id)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(stats_text)
        tmp_path = f.name
    
    try:
        with open(tmp_path, 'rb') as f:
            context.bot.send_document(
                chat_id=user_id,
                document=f,
                filename=f"stats_{user_id}_{int(time.time())}.txt",
                caption="📊 Ваша статистика"
            )
    except Exception as e:
        logger.error(f"Error sending stats: {e}")
    
    time.sleep(1)
    try:
        os.unlink(tmp_path)
    except:
        pass
    
    safe_send_message(
        context.bot, user_id,
        "📊 Статистика отправлена.",
        reply_markup=back("profile")
    )

def withdraw(update, context):
    """Вывод реферального баланса"""
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    ref_info = get_referral_info(user_id)
    balance = ref_info[1] if ref_info else 0
    
    if balance < 5:
        safe_edit_message(
            query,
            f"❌ Минимальная сумма для вывода: 5$\nВаш баланс: ${balance:.2f}",
            reply_markup=back("profile")
        )
        return
    
    # Отправляем уведомление в поддержку
    from config import SUPPORT, OWNER_ID
    text = (
        f"💰 **Запрос на вывод средств**\n\n"
        f"👤 Пользователь: @{query.from_user.username or 'нет'}\n"
        f"🆔 ID: `{user_id}`\n"
        f"💵 Сумма: ${balance:.2f}\n\n"
        f"Контакты: {SUPPORT}"
    )
    
    safe_send_message(context.bot, OWNER_ID, text)
    
    safe_edit_message(
        query,
        f"✅ Запрос на вывод ${balance:.2f} отправлен!\n"
        f"Ожидайте, с вами свяжется {SUPPORT}",
        reply_markup=back("profile")
    )
    
    logger.info(f"Withdrawal request: user {user_id}, amount ${balance}")