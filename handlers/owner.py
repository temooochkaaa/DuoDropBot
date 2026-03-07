import time
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, TimedOut
from database import get_cursor
from keyboards import owner_panel_menu, back
from config import BROADCAST_DELAY

logger = logging.getLogger(__name__)

def owner_panel(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "👑 **Панель владельца**",
        parse_mode='Markdown',
        reply_markup=owner_panel_menu()
    )

def owner_stats(update, context):
    query = update.callback_query
    query.answer()
    
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM users WHERE role='cold'")
        cold_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM users WHERE role='helper'")
        helper_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM users WHERE role='owner'")
        owner_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM numbers WHERE status='waiting'")
        waiting = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM numbers WHERE status='in_progress'")
        in_progress = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM numbers WHERE status='activated'")
        activated = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM numbers WHERE status='crashed'")
        crashed = cur.fetchone()[0]
        
        today = int(time.time()) - 86400
        cur.execute("SELECT COUNT(*) FROM numbers WHERE created_at > %s", (today,))
        today_numbers = cur.fetchone()[0]
    
    text = (
        f"📊 **СТАТИСТИКА БОТА**\n\n"
        f"👥 **Пользователи:**\n"
        f"• Всего: {total_users}\n"
        f"• Холодка: {cold_count}\n"
        f"• Помощники: {helper_count}\n"
        f"• Владельцы: {owner_count}\n\n"
        f"📱 **Номера:**\n"
        f"• В очереди: {waiting}\n"
        f"• В работе: {in_progress}\n"
        f"• Активировано: {activated}\n"
        f"• Слетело: {crashed}\n\n"
        f"📈 **За сегодня:** {today_numbers}"
    )
    
    buttons = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="owner_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="owner_panel")]
    ]
    
    query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def manage_roles(update, context):
    query = update.callback_query
    query.answer()
    
    with get_cursor() as cur:
        cur.execute("SELECT id, username, first_name, role FROM users ORDER BY role, id LIMIT 20")
        users = cur.fetchall()
    
    text = "👥 **Управление ролями**\n\n"
    for u in users:
        name = f"@{u[1]}" if u[1] else u[2]
        text += f"• {name} (ID: {u[0]}) - **{u[3]}**\n"
    
    text += "\n📝 **Изменить роль:**\n`роль ID`\nПример: `cold 123456789`\n\nДоступные роли: `owner`, `helper`, `cold`, `user`"
    
    query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=back("owner_panel")
    )
    
    from states import WAITING_ROLE_ID
    return WAITING_ROLE_ID

def process_role_change(update, context):
    try:
        text = update.message.text.strip().split()
        if len(text) != 2:
            update.message.reply_text("❌ Формат: роль ID")
            return -1
        
        role = text[0].lower()
        user_id = int(text[1])
        
        if role not in ['owner', 'helper', 'cold', 'user']:
            update.message.reply_text("❌ Неверная роль. Доступны: owner, helper, cold, user")
            return -1
        
        with get_cursor(commit=True) as cur:
            cur.execute("UPDATE users SET role=%s WHERE id=%s", (role, user_id))
        
        try:
            from keyboards import main_menu
            context.bot.send_message(
                user_id,
                f"🔄 Ваша роль изменена на {role}",
                reply_markup=main_menu(role)
            )
        except:
            pass
        
        update.message.reply_text(f"✅ Роль {user_id} изменена на {role}")
        
    except ValueError:
        update.message.reply_text("❌ Неверный ID. Введите число.")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}")
    
    return -1

def broadcast_start(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "📢 Введите сообщение для рассылки всем пользователям:",
        reply_markup=back("owner_panel")
    )
    from states import WAITING_BROADCAST
    return WAITING_BROADCAST

def broadcast_process(update, context):
    text = update.message.text
    
    with get_cursor() as cur:
        cur.execute("SELECT id FROM users WHERE role='user'")
        users = cur.fetchall()
    
    if not users:
        update.message.reply_text("📭 Нет пользователей для рассылки.")
        return -1
    
    sent = 0
    failed = 0
    start_time = time.time()
    
    for u in users:
        retries = 3
        while retries > 0:
            try:
                context.bot.send_message(
                    u[0],
                    f"📢 **Сообщение от администрации:**\n\n{text}",
                    parse_mode='Markdown'
                )
                sent += 1
                time.sleep(BROADCAST_DELAY)
                break
            except RetryAfter as e:
                wait_time = e.retry_after
                logger.warning(f"Flood wait for {wait_time} seconds")
                time.sleep(wait_time)
                retries -= 1
            except TimedOut:
                logger.warning("Timeout, retrying...")
                time.sleep(1)
                retries -= 1
            except Exception as e:
                failed += 1
                logger.error(f"Broadcast failed to {u[0]}: {e}")
                break
    
    elapsed = time.time() - start_time
    
    result_text = (
        f"✅ **Рассылка завершена!**\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Не удалось: {failed}\n"
        f"⏱ Время: {elapsed:.1f} сек"
    )
    
    update.message.reply_text(
        result_text,
        parse_mode='Markdown',
        reply_markup=back("owner_panel")
    )
    
    logger.info(f"Broadcast completed: {sent} sent, {failed} failed in {elapsed:.1f}s")
    return -1