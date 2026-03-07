from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from keyboards import main_menu, back
from utils.roles import get_role
from config import SUPPORT, GROUP_LINK, REPUTATION_LINK, ADAPTER_LINK

def back_to_menu(update, context):
    query = update.callback_query
    query.answer()
    role = get_role(query.from_user.id) or 'user'
    query.edit_message_text(
        "🔙 Главное меню",
        reply_markup=main_menu(role)
    )

def support(update, context):
    query = update.callback_query
    query.answer()
    
    text = (
        f"🔰 **Поддержка:** {SUPPORT}\n\n"
        f"📢 **Наша группа:** [ссылка]({GROUP_LINK})\n"
        f"🤖 **Adapter:** [@DuoDrop]({ADAPTER_LINK})\n"
        f"⭐ **Репутация:** [ссылка]({REPUTATION_LINK})"
    )
    
    query.edit_message_text(
        text,
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=back("menu")
    )