import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, CallbackContext
import config

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_FOR_NUMBER, WAITING_FOR_TYPE, WAITING_FOR_MAX_NUMBER, WAITING_FOR_AGREEMENT = range(4)

class Database:
    def __init__(self, db_name='bot.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                role TEXT DEFAULT 'user',
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                referred_by INTEGER,
                referral_balance REAL DEFAULT 0,
                accepted_agreement BOOLEAN DEFAULT 0
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone_number TEXT,
                platform TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                taken_by INTEGER
            )
        ''')
        self.conn.commit()
    
    def add_user(self, user_id, username, first_name, referrer_id=None):
        self.cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)',
                          (user_id, username, first_name, referrer_id))
        self.conn.commit()
    
    def accept_agreement(self, user_id):
        self.cursor.execute('UPDATE users SET accepted_agreement = 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def check_agreement(self, user_id):
        self.cursor.execute('SELECT accepted_agreement FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result and result[0] == 1
    
    def get_user_role(self, user_id):
        self.cursor.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 'user'
    
    def set_user_role(self, user_id, role):
        self.cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
        self.conn.commit()
    
    def check_duplicate(self, user_id, phone_number):
        self.cursor.execute('''
            SELECT id FROM numbers 
            WHERE user_id = ? AND phone_number = ? AND status IN ('pending', 'in_progress')
        ''', (user_id, phone_number))
        return self.cursor.fetchone() is not None
    
    def add_number(self, user_id, phone_number, platform):
        if self.check_duplicate(user_id, phone_number):
            return False
        self.cursor.execute('''
            INSERT INTO numbers (user_id, phone_number, platform, status)
            VALUES (?, ?, ?, 'pending')
        ''', (user_id, phone_number, platform))
        self.conn.commit()
        return True

db = Database()

def get_main_keyboard(role):
    keyboard = []
    if role == 'user':
        keyboard = [
            [InlineKeyboardButton("📱 Сдать номер", callback_data="menu_submit")],
            [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile")],
            [InlineKeyboardButton("🔰 Поддержка", callback_data="menu_support")]
        ]
    elif role == 'cold':
        keyboard = [
            [InlineKeyboardButton("📋 Очередь WhatsApp", callback_data="cold_wa_queue"),
             InlineKeyboardButton("📋 Очередь MAX", callback_data="cold_max_queue")],
            [InlineKeyboardButton("📋 Мои WhatsApp", callback_data="cold_my_wa"),
             InlineKeyboardButton("📋 Мои MAX", callback_data="cold_my_max")],
            [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"),
             InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
        ]
    elif role in ['helper', 'owner']:
        keyboard = [
            [InlineKeyboardButton("👑 Админ панель", callback_data="menu_admin")],
            [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"),
             InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
        ]
    return InlineKeyboardMarkup(keyboard)

def get_agreement_text():
    return "Пользовательское соглашение..."

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    referrer_id = context.args[0] if context.args else None
    db.add_user(user.id, user.username, user.first_name, referrer_id)
    
    if not db.check_agreement(user.id):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Принимаю", callback_data="accept_agreement")]])
        update.message.reply_text(get_agreement_text(), reply_markup=keyboard)
        return WAITING_FOR_AGREEMENT
    
    role = db.get_user_role(user.id)
    update.message.reply_text(f"👋 Привет, {user.first_name}!", reply_markup=get_main_keyboard(role))

def handle_agreement(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    db.accept_agreement(query.from_user.id)
    role = db.get_user_role(query.from_user.id)
    query.edit_message_text("✅ Соглашение принято!", reply_markup=get_main_keyboard(role))
    return ConversationHandler.END

def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    user_id = query.from_user.id
    role = db.get_user_role(user_id)
    
    if data == "back_to_main":
        query.edit_message_text("Главное меню", reply_markup=get_main_keyboard(role))
    
    elif data == "menu_submit":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 WhatsApp", callback_data="submit_whatsapp"),
             InlineKeyboardButton("📲 MAX", callback_data="submit_max")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ])
        query.edit_message_text("Выберите платформу:", reply_markup=keyboard)
    
    elif data == "menu_profile":
        text = f"👤 Профиль\nID: {user_id}\nРоль: {role}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
        query.edit_message_text(text, reply_markup=keyboard)
    
    elif data == "menu_support":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
        query.edit_message_text("🔰 Поддержка: @popopep", reply_markup=keyboard)
    
    elif data == "submit_whatsapp":
        query.edit_message_text("📞 Введите номер для WhatsApp:")
        return WAITING_FOR_NUMBER
    
    elif data == "submit_max":
        query.edit_message_text("📞 Введите номер для MAX:")
        return WAITING_FOR_MAX_NUMBER

def handle_number_input(update: Update, context: CallbackContext):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        update.message.reply_text("❌ Неверный формат. Попробуйте снова.")
        return WAITING_FOR_NUMBER
    
    user_id = update.effective_user.id
    if db.add_number(user_id, phone, 'whatsapp'):
        update.message.reply_text("✅ Номер принят!")
    else:
        update.message.reply_text("❌ Этот номер уже в обработке.")
    
    role = db.get_user_role(user_id)
    update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(role))
    return ConversationHandler.END

def handle_max_input(update: Update, context: CallbackContext):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        update.message.reply_text("❌ Неверный формат. Попробуйте снова.")
        return WAITING_FOR_MAX_NUMBER
    
    user_id = update.effective_user.id
    if db.add_number(user_id, phone, 'max'):
        update.message.reply_text("✅ Номер принят!")
    else:
        update.message.reply_text("❌ Этот номер уже в обработке.")
    
    role = db.get_user_role(user_id)
    update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(role))
    return ConversationHandler.END

def handle_role_command(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) != 2 or parts[0] != 'owner':
        return
    
    try:
        target_id = int(parts[1])
        db.set_user_role(target_id, 'owner')
        update.message.reply_text(f"✅ Пользователь {target_id} теперь владелец!")
    except:
        update.message.reply_text("❌ Неверный ID")

def main():
    updater = Updater(config.BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(MessageHandler(Filters.regex('^owner \d+$'), handle_role_command))
    
    dp.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^accept_agreement$')],
        states={WAITING_FOR_AGREEMENT: [CallbackQueryHandler(handle_agreement)]},
        fallbacks=[]
    ))
    
    dp.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^submit_whatsapp$')],
        states={WAITING_FOR_NUMBER: [MessageHandler(Filters.text & ~Filters.command, handle_number_input)]},
        fallbacks=[]
    ))
    
    dp.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^submit_max$')],
        states={WAITING_FOR_MAX_NUMBER: [MessageHandler(Filters.text & ~Filters.command, handle_max_input)]},
        fallbacks=[]
    ))
    
    dp.add_handler(CallbackQueryHandler(handle_callback))
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()