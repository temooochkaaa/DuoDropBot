import logging
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler, Filters
)

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
from handlers.profile import profile, my_stats
from handlers.queue import check_queue
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
    owner_panel, manage_roles, process_role_change,
    broadcast_start, broadcast_process, owner_stats
)
from jobs.queue_checker import check_queue_job, queue_action

from states import (
    WAITING_NUMBER_WHATSAPP, WAITING_NUMBER_MAX, WAITING_PHOTO,
    WAITING_EXTRA, WAITING_BROADCAST, WAITING_ROLE_ID, WAITING_REMOVE_ID
)


def cancel(update, context):
    update.message.reply_text("❌ Действие отменено.")
    from keyboards import main_menu
    from utils.roles import get_role
    role = get_role(update.effective_user.id) or 'user'
    update.message.reply_text("Главное меню:", reply_markup=main_menu(role))
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


def shutdown():
    logger.info("Shutting down...")
    try:
        db_pool.close_all()
    except Exception as e:
        logger.error(f"Error closing database pool: {e}")


def cleanup_job(context):
    """Фоновая очистка старых записей"""
    logger.info("Running cleanup job...")
    cleanup_old_numbers()


def main():
    init_db()
    # Пересчитываем очередь при старте
    reorder_queue()
    logger.info("Database initialized and queue reordered")
    
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_error_handler(error_handler)
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("cancel", cancel))
    
    dp.add_handler(CallbackQueryHandler(accept_agreement, pattern="^(accept|decline)$"))
    dp.add_handler(CallbackQueryHandler(back_to_menu, pattern="^menu$"))
    dp.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    dp.add_handler(CallbackQueryHandler(profile, pattern="^profile$"))
    dp.add_handler(CallbackQueryHandler(my_stats, pattern="^my_stats$"))
    dp.add_handler(CallbackQueryHandler(check_queue, pattern="^check_queue$"))
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
    dp.add_handler(CallbackQueryHandler(request_number, pattern="^req_"))
    dp.add_handler(CallbackQueryHandler(free_numbers, pattern="^free_numbers$"))
    dp.add_handler(CallbackQueryHandler(numbers_pagination, pattern="^numbers_(prev|next)$"))
    dp.add_handler(CallbackQueryHandler(my_numbers, pattern="^my_numbers$"))
    dp.add_handler(CallbackQueryHandler(view_number, pattern="^view_number_"))
    
    # Изменено: общий обработчик для взятия номера
    dp.add_handler(CallbackQueryHandler(take_number, pattern="^take_number_"))
    
    photo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(take_number, pattern="^take_(code|qr)_")],
        states={WAITING_PHOTO: [MessageHandler(Filters.photo, receive_photo)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="photo_conv"
    )
    dp.add_handler(photo_conv)
    
    extra_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(request_extra_info, pattern="^req_extra_")],
        states={WAITING_EXTRA: [MessageHandler(Filters.text & ~Filters.command, receive_extra_info)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="extra_conv"
    )
    dp.add_handler(extra_conv)
    
    extra_reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(process_extra_reply, pattern="^extra_reply_")],
        states={WAITING_EXTRA: [MessageHandler(Filters.text & ~Filters.command, save_extra_reply)]},
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel)],
        conversation_timeout=300,
        name="extra_reply_conv"
    )
    dp.add_handler(extra_reply_conv)
    
    dp.add_handler(CallbackQueryHandler(code_entered, pattern="^code_entered_"))
    dp.add_handler(CallbackQueryHandler(set_status, pattern="^(activated|failed|crashed)_"))
    dp.add_handler(CallbackQueryHandler(retry_number, pattern="^retry_"))
    dp.add_handler(CallbackQueryHandler(cancel_number, pattern="^cancel_"))
    
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
    
    dp.add_handler(CallbackQueryHandler(queue_action, pattern="^(keep|remove)_"))
    
    jq = updater.job_queue
    jq.run_repeating(check_queue_job, interval=QUEUE_CHECK_INTERVAL)
    jq.run_repeating(cleanup_job, interval=CLEANUP_INTERVAL, first=3600)  # Запустить через час после старта
    
    logger.info("Bot started")
    updater.start_polling()
    
    try:
        updater.idle()
    finally:
        shutdown()


if __name__ == "__main__":
    main()