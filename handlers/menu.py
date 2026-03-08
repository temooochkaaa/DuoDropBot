from keyboards import main_menu, back
from utils.roles import get_role
from config import SUPPORT, GROUP_LINK, REPUTATION_LINK, ADAPTER_LINK
from main import safe_edit_message

def back_to_menu(update, context):
    query = update.callback_query
    query.answer()
    role = get_role(query.from_user.id) or 'user'
    safe_edit_message(
        query,
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
    
    safe_edit_message(
        query,
        text,
        reply_markup=back()
    )