import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_cursor, reorder_queue
from keyboards import back, queue_menu, number_detail_menu, main_menu
from datetime import datetime
from config import TIMEZONE
from utils.helpers import safe_edit_message
from utils.roles import get_role

logger = logging.getLogger(__name__)


def check_queue(update, context):

    query = update.callback_query
    query.answer()

    safe_edit_message(
        query,
        "📊 Выберите очередь:",
        reply_markup=queue_menu()
    )


def show_queue(update, context):

    query = update.callback_query
    query.answer()

    platform = query.data.split("_")[2]
    user_id = query.from_user.id

    with get_cursor() as cur:

        cur.execute("""
        SELECT id, phone, queue_position, created_at
        FROM numbers
        WHERE user_id=%s AND platform=%s AND status='waiting' AND in_queue=1
        ORDER BY queue_position
        """, (user_id, platform))

        rows = cur.fetchall()

    if not rows:

        safe_edit_message(
            query,
            f"📭 У вас нет номеров в очереди {platform.upper()}",
            reply_markup=back("check_queue")
        )
        return

    text = f"📊 Очередь {platform.upper()}:\n\n"

    buttons = []

    for i, r in enumerate(rows, start=1):

        number_id, phone, position, created = r

        created_time = datetime.fromtimestamp(
            created, TIMEZONE
        ).strftime('%d.%m %H:%M')

        text += f"{i}. 📞 {phone} — позиция {position} ({created_time})\n"

        buttons.append([
            InlineKeyboardButton(
                f"📞 {phone}",
                callback_data=f"queue_detail_{number_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("⬅ Назад", callback_data="check_queue")
    ])

    safe_edit_message(
        query,
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def queue_detail(update, context):

    query = update.callback_query
    query.answer()

    number_id = int(query.data.split("_")[2])
    user_id = query.from_user.id

    with get_cursor() as cur:

        cur.execute("""
        SELECT phone, platform, queue_position, created_at
        FROM numbers
        WHERE id=%s AND user_id=%s
        """, (number_id, user_id))

        result = cur.fetchone()

    if not result:

        safe_edit_message(query, "❌ Номер не найден")
        return

    phone, platform, position, created = result

    created_time = datetime.fromtimestamp(
        created, TIMEZONE
    ).strftime('%d.%m.%Y %H:%M')

    text = (
        f"📞 Номер: {phone}\n"
        f"📱 Платформа: {platform.upper()}\n"
        f"🔢 Позиция: {position}\n"
        f"📅 Добавлен: {created_time}\n\n"
        f"Удалить номер из очереди?"
    )

    safe_edit_message(
        query,
        text,
        reply_markup=number_detail_menu(number_id)
    )


def delete_from_queue(update, context):

    query = update.callback_query
    query.answer()

    user_id = query.from_user.id
    number_id = int(query.data.split("_")[2])

    try:

        with get_cursor(commit=True) as cur:

            cur.execute("""
            SELECT platform
            FROM numbers
            WHERE id=%s AND user_id=%s AND status='waiting'
            """, (number_id, user_id))

            result = cur.fetchone()

            if not result:

                context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Номер не найден"
                )
                return

            platform = result[0]

            cur.execute("""
            UPDATE numbers
            SET status='cancelled',
                in_queue=0,
                taken_by=NULL
            WHERE id=%s AND user_id=%s
            """, (number_id, user_id))

            reorder_queue(platform)

        try:
            query.message.delete()
        except:
            pass

        role = get_role(user_id) or "user"

        context.bot.send_message(
            chat_id=user_id,
text="✅ Номер удалён из очереди",
            reply_markup=main_menu(role)
        )

    except Exception as e:

        logger.error(f"Delete queue error: {e}", exc_info=True)

        context.bot.send_message(
            chat_id=user_id,
            text="❌ Ошибка удаления номера"
        )