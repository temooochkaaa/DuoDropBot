import logging

logger = logging.getLogger(__name__)

def safe_edit_message(query, text, reply_markup=None):
    """Безопасное редактирование сообщения с игнорированием ошибки Message is not modified"""
    try:
        if reply_markup:
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            query.edit_message_text(text, parse_mode='Markdown')
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error editing message: {e}")

def safe_send_message(bot, chat_id, text, reply_markup=None, parse_mode='Markdown'):
    """Безопасная отправка сообщения с try/except"""
    try:
        if reply_markup:
            bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            bot.send_message(chat_id, text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")