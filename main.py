import logging
import requests
import time
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler, Filters
)
from telegram.error import TelegramError

from config import BOT_TOKEN, QUEUE_CHECK_INTERVAL, CLEANUP_INTERVAL, OWNER_ID
from database import init_db, db_pool, reorder_queue, cleanup_old_numbers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from handlers.start import start, accept_agreement
from handlers.menu import back_to_menu, support
from handlers.submit import (
    submit_menu_handler, submit_whatsapp, submit_max, 
    process_whatsapp_number, process_max_number
)
from handlers.profile import profile, my_stats, withdraw
from handlers.queue import check_queue, show_queue, queue_detail, delete_from_queue
from handlers.cold import (
    cold_panel, request_number, free_numbers, view_number, 
    take_number, numbers_pagination
)
from handlers.cold_actions import (
    receive_photo, code_entered, set_status, retry_number, cancel_number,
    request_extra_info, receive_extra_info, process_extra_reply, save_extra_reply
)
from handlers.numbers import my_numbers
from handlers.helper import (
    helper_panel, stats_whatsapp, stats_max, all_numbers,
    all_pagination, remove_number_start, remove_number_process
)
from handlers.owner import (
    owner_panel, owner_stats, manage_roles, process_role_change,
    broadcast_start, broadcast_process
)
from jobs.queue_checker import check_queue_job, queue_action
from jobs.stale_checker import check_stale_job
from utils.roles import get_role

from states import (
    WAITING_NUMBER_WHATSAPP, WAITING_NUMBER_MAX, WAITING_PHOTO,
    WAITING_EXTRA, WAITING_BROADCAST, WAITING_ROLE_ID, WAITING_REMOVE_ID,
    QUEUE_STATE
)


def force_delete_webhook():
    """Принудительное удаление вебхука перед запуском"""
    for i in range(3):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
            response = requests.get(url)
            logger.info(f"Delete webhook attempt {i+1}: {response.json()}")
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")


def cancel(update, context):
    try:
        if update.message:
            update.message.reply_text("❌ Действие отменено.")
        role = get_role(update.effective_user.id) or 'user'
        from keyboards import main_menu
        if update.message:
            update.message.reply_text("Главное меню:", reply_markup=main_menu(role))
        elif update.callback_query:
            update.callback_query.message.reply_text("Главное меню:", reply_markup=main_menu(role))
    except:
        pass
    return ConversationHandler.END


def error_handler(update, context):
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    try:
        if update and update.effective_user and update.effective_user.id != OWNER_ID:
            context.bot.send_message(
                OWNER_ID, 
                f"❌ **Ошибка бота**\n\n{context.error}",
                parse_mode='Markdown'
            )
    except:
        pass


def safe_edit_message(query, text, reply_markup=None):
    try:
        if reply_markup:
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            query.edit_message_text(text, parse_mode='Markdown')
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error editing message: {e}")


def safe_send_message(bot, chat_id, text, reply_markup=None, parse_mode='Markdown'):
    try:
        if reply_markup:
            bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            bot.send_message(chat_id, text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")


def check_cooldown(user_id, cooldown_type='button'):
    with get_cursor() as cur:
        cur.execute(f"SELECT last_{cooldown_type} FROM users WHERE id=%s", (user_id,))
        result = cur.fetchone()
        last = result[0] if result else 0
        now = int(time.time())
        
        from config import BUTTON_COOLDOWN, REQUEST_NUMBER_COOLDOWN
        cd = BUTTON_COOLDOWN if cooldown_type == 'button' else REQUEST_NUMBER_COOLDOWN
        
        if now - last < cd:
            return False, cd - (now - last)
        
        return True, 0


def update_cooldown(user_id, cooldown_type='button'):
    with get_cursor(commit=True) as cur:
        cur.execute(f"UPDATE users SET last_{cooldown_type}=%s WHERE id=%s", 
                   (int(time.time()), user_id))


def shutdown():
    logger.info("Shutting down...")
    try:
        db_pool.close_all()
    except Exception as e:
        logger.error(f"Error closing database pool: {e}")


def cleanup_job(context):
    logger.info("Running cleanup job...")
    cleanup_old_numbers()


def main():
    # Принудительно удаляем вебхук перед запуском
    force_delete_webhook()
    
    init_db()
    reorder_queue()
    logger.info("Database initialized and queue reordered")
    
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_error_handler(error_handler)
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("cancel", cancel))
    
    dp.add_handler(CallbackQueryHandler(accept_agreement, pattern="^accept_agreement$"))
    dp.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    dp.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    dp.add_handler(CallbackQueryHandler(profile, pattern="^profile$"))
    dp.add_handler(CallbackQueryHandler(my_stats, pattern="^my_stats$"))
    dp.add_handler(CallbackQueryHandler(withdraw, pattern="^withdraw$"))
    
    # ConversationHandler для очереди
    queue_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_queue, pattern="^check_queue$")],
        states={
            QUEUE_STATE: [
                CallbackQueryHandler(show_queue, pattern="^show_queue_(whatsapp|max)$"),
                CallbackQueryHandler(queue_detail, pattern="^queue_detail_\\d+$"),
                CallbackQueryHandler(delete_from_queue, pattern="^delete_queue_\\d+$")
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
        conversation_timeout=300,
        name="queue_conv"
    )
    dp.add_handler(queue_conv)
    
    dp.add_handler(CallbackQueryHandler(submit_menu_handler, pattern="^submit_menu$"))
    
    whatsapp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(submit_whatsapp, pattern="^submit_whatsapp$")],
        states={WAITING_NUMBER_WHATSAPP: [MessageHandler(Filters.text & ~Filters.command, process_whatsapp_number)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="whatsapp_conv"
    )
    dp.add_handler(whatsapp_conv)
    
    max_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(submit_max, pattern="^submit_max$")],
        states={WAITING_NUMBER_MAX: [MessageHandler(Filters.text & ~Filters.command, process_max_number)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="max_conv"
    )
    dp.add_handler(max_conv)
    
    dp.add_handler(CallbackQueryHandler(cold_panel, pattern="^cold_panel$"))
    dp.add_handler(CallbackQueryHandler(request_number, pattern="^request_number_(whatsapp|max)$"))
    dp.add_handler(CallbackQueryHandler(free_numbers, pattern="^free_numbers_(whatsapp|max)$"))
    dp.add_handler(CallbackQueryHandler(numbers_pagination, pattern="^numbers_(prev|next)_(whatsapp|max)$"))
    dp.add_handler(CallbackQueryHandler(my_numbers, pattern="^my_numbers$"))
    dp.add_handler(CallbackQueryHandler(view_number, pattern="^view_number_\\d+$"))
    dp.add_handler(CallbackQueryHandler(take_number, pattern="^take_(code|qr|max)_\\d+$"))
    
    photo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(take_number, pattern="^take_(code|qr)_\\d+$")],
        states={WAITING_PHOTO: [MessageHandler(Filters.photo, receive_photo)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="photo_conv"
    )
    dp.add_handler(photo_conv)
    
    extra_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(request_extra_info, pattern="^request_extra_\\d+$")],
        states={WAITING_EXTRA: [MessageHandler(Filters.text & ~Filters.command, receive_extra_info)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="extra_conv"
    )
    dp.add_handler(extra_conv)
    
    extra_reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(process_extra_reply, pattern="^reply_extra_\\d+$")],
        states={WAITING_EXTRA: [MessageHandler(Filters.text & ~Filters.command, save_extra_reply)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="extra_reply_conv"
    )
    dp.add_handler(extra_reply_conv)
    
    dp.add_handler(CallbackQueryHandler(code_entered, pattern="^code_entered_\\d+$"))
    dp.add_handler(CallbackQueryHandler(set_status, pattern="^(activate|fail|crashed)_\\d+$"))
    dp.add_handler(CallbackQueryHandler(retry_number, pattern="^retry_number_\\d+$"))
    dp.add_handler(CallbackQueryHandler(cancel_number, pattern="^cancel_number_\\d+$"))
    
    dp.add_handler(CallbackQueryHandler(helper_panel, pattern="^helper_panel$"))
    dp.add_handler(CallbackQueryHandler(stats_whatsapp, pattern="^stats_whatsapp$"))
    dp.add_handler(CallbackQueryHandler(stats_max, pattern="^stats_max$"))
    dp.add_handler(CallbackQueryHandler(all_numbers, pattern="^all_numbers$"))
    dp.add_handler(CallbackQueryHandler(all_pagination, pattern="^all_(prev|next)$"))
    
    remove_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_number_start, pattern="^remove_number$")],
        states={WAITING_REMOVE_ID: [MessageHandler(Filters.text & ~Filters.command, remove_number_process)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="remove_conv"
    )
    dp.add_handler(remove_conv)
    
    dp.add_handler(CallbackQueryHandler(owner_panel, pattern="^owner_panel$"))
    dp.add_handler(CallbackQueryHandler(owner_stats, pattern="^owner_stats$"))
    
    role_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(manage_roles, pattern="^manage_roles$")],
        states={WAITING_ROLE_ID: [MessageHandler(Filters.text & ~Filters.command, process_role_change)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="role_conv"
    )
    dp.add_handler(role_conv)
    
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^broadcast$")],
        states={WAITING_BROADCAST: [MessageHandler(Filters.text & ~Filters.command, broadcast_process)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="broadcast_conv"
    )
    dp.add_handler(broadcast_conv)
    
    dp.add_handler(CallbackQueryHandler(queue_action, pattern="^(keep|remove)_\\d+$"))
    
    jq = updater.job_queue
    jq.run_repeating(check_queue_job, interval=QUEUE_CHECK_INTERVAL)
    jq.run_repeating(check_stale_job, interval=300, first=60)
    jq.run_repeating(cleanup_job, interval=CLEANUP_INTERVAL, first=3600)
    
    logger.info("Bot started")
    updater.start_polling()
    
    try:
        updater.idle()
    finally:
        shutdown()


if __name__ == "__main__":
    main()