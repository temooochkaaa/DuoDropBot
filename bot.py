import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, CallbackContext
import config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(
    WAITING_FOR_NUMBER,
    WAITING_FOR_TYPE,
    WAITING_FOR_CODE,
    WAITING_FOR_QR_PHOTO,
    WAITING_FOR_CODE_PHOTO,
    WAITING_FOR_RETRY_DECISION,
    WAITING_FOR_MAX_NUMBER,
    WAITING_FOR_MAX_CODE,
    WAITING_FOR_MAX_EXTRA_INFO,
    WAITING_FOR_MAX_USER_REPLY,
    WAITING_FOR_AGREEMENT,
    WAITING_FOR_FINE_AMOUNT,
    WAITING_FOR_FINE_REASON,
    WAITING_FOR_FINE_USER,
    WAITING_FOR_FINE_RESET,
    WAITING_FOR_ROLE_CHANGE,
    WAITING_FOR_QUEUE_REMOVE
) = range(17)

# Класс для работы с базой данных
class Database:
    def __init__(self, db_name='whatsapp_bot.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        # Таблица пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT DEFAULT 'user',
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_numbers INTEGER DEFAULT 0,
                total_working_time INTEGER DEFAULT 0,
                total_crashed INTEGER DEFAULT 0,
                today_numbers INTEGER DEFAULT 0,
                today_working_time INTEGER DEFAULT 0,
                today_crashed INTEGER DEFAULT 0,
                total_max_numbers INTEGER DEFAULT 0,
                total_max_working_time INTEGER DEFAULT 0,
                total_max_crashed INTEGER DEFAULT 0,
                today_max_numbers INTEGER DEFAULT 0,
                today_max_working_time INTEGER DEFAULT 0,
                today_max_crashed INTEGER DEFAULT 0,
                referred_by INTEGER,
                referral_count INTEGER DEFAULT 0,
                referral_balance REAL DEFAULT 0,
                total_referral_earned REAL DEFAULT 0,
                qualified_referrals INTEGER DEFAULT 0,
                fine_amount REAL DEFAULT 0,
                total_fines REAL DEFAULT 0,
                accepted_agreement BOOLEAN DEFAULT 0,
                agreement_accepted_date TIMESTAMP,
                last_reset_date DATE
            )
        ''')
        
        # Таблица рефералов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                referred_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                numbers_submitted INTEGER DEFAULT 0,
                qualified_date TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                FOREIGN KEY (referred_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица штрафов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                issued_by INTEGER,
                amount REAL,
                reason TEXT,
                issued_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                paid_date TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (issued_by) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица логов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT,
                details TEXT,
                platform TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица номеров WhatsApp
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                code_sent_at TIMESTAMP,
                code_entered_at TIMESTAMP,
                activated_at TIMESTAMP,
                crashed_at TIMESTAMP,
                total_work_time INTEGER DEFAULT 0,
                code_text TEXT,
                qr_photo_id TEXT,
                code_photo_id TEXT,
                request_type TEXT,
                taken_by INTEGER,
                queue_position INTEGER,
                in_queue BOOLEAN DEFAULT 1,
                last_queue_notification TIMESTAMP,
                platform TEXT DEFAULT 'whatsapp',
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (taken_by) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица MAX аккаунтов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS max_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                code_requested_at TIMESTAMP,
                code_received_at TIMESTAMP,
                activated_at TIMESTAMP,
                crashed_at TIMESTAMP,
                total_work_time INTEGER DEFAULT 0,
                code_text TEXT,
                taken_by INTEGER,
                queue_position INTEGER,
                in_queue BOOLEAN DEFAULT 1,
                last_queue_notification TIMESTAMP,
                waiting_for_code BOOLEAN DEFAULT 0,
                waiting_for_extra BOOLEAN DEFAULT 0,
                extra_request TEXT,
                last_extra_request TIMESTAMP,
                platform TEXT DEFAULT 'max',
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (taken_by) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица группы
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_info (
                id INTEGER PRIMARY KEY,
                group_id INTEGER,
                group_name TEXT
            )
        ''')
        
        self.conn.commit()
    
    def add_user(self, user_id, username, first_name, last_name, referrer_id=None):
        self.cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, last_reset_date, referred_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, datetime.now().date(), referrer_id))
        self.conn.commit()
        
        if referrer_id and referrer_id != user_id:
            self.cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id, status)
                VALUES (?, ?, 'pending')
            ''', (referrer_id, user_id))
            self.conn.commit()
    
    def check_agreement(self, user_id):
        self.cursor.execute('SELECT accepted_agreement FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result and result[0] == 1
    
    def accept_agreement(self, user_id):
        self.cursor.execute('''
            UPDATE users 
            SET accepted_agreement = 1, agreement_accepted_date = ?
            WHERE user_id = ?
        ''', (datetime.now(), user_id))
        self.conn.commit()
    
    def get_user_role(self, user_id):
        self.cursor.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 'user'
    
    def add_log(self, user_id, username, action, details, platform='system'):
        try:
            self.cursor.execute('''
                INSERT INTO logs (user_id, username, action, details, platform, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, action, details, platform, datetime.now()))
            self.conn.commit()
            
            self.cursor.execute('''
                DELETE FROM logs WHERE timestamp < datetime('now', '-3 days')
            ''')
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error adding log: {e}")
    
    def get_logs(self, days=3):
        self.cursor.execute('''
            SELECT * FROM logs WHERE timestamp >= datetime('now', ?)
            ORDER BY timestamp DESC LIMIT 100
        ''', (f'-{days} days',))
        return self.cursor.fetchall()
    
    def get_all_cold_staff(self):
        self.cursor.execute('SELECT user_id FROM users WHERE role IN ("cold", "helper", "owner")')
        return [row[0] for row in self.cursor.fetchall()]
    
    def get_group_id(self):
        self.cursor.execute('SELECT group_id FROM group_info WHERE id = 1')
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def set_group_id(self, group_id, group_name):
        self.cursor.execute('''
            INSERT OR REPLACE INTO group_info (id, group_id, group_name)
            VALUES (1, ?, ?)
        ''', (group_id, group_name))
        self.conn.commit()
    
    def create_whatsapp_request(self, user_id, phone_number, request_type):
        self.cursor.execute('SELECT MAX(queue_position) FROM numbers WHERE status = "pending" AND in_queue = 1 AND platform = "whatsapp"')
        max_pos = self.cursor.fetchone()[0]
        next_position = (max_pos or 0) + 1
        
        self.cursor.execute('''
            INSERT INTO numbers (user_id, phone_number, status, request_type, queue_position, in_queue, platform)
            VALUES (?, ?, 'pending', ?, ?, 1, 'whatsapp')
        ''', (user_id, phone_number, request_type, next_position))
        self.conn.commit()
        return self.cursor.lastrowid, next_position
    
    def create_max_request(self, user_id, phone_number):
        self.cursor.execute('SELECT MAX(queue_position) FROM max_accounts WHERE status = "pending" AND in_queue = 1')
        max_pos = self.cursor.fetchone()[0]
        next_position = (max_pos or 0) + 1
        
        self.cursor.execute('''
            INSERT INTO max_accounts (user_id, phone_number, status, queue_position, in_queue)
            VALUES (?, ?, 'pending', ?, 1)
        ''', (user_id, phone_number, next_position))
        self.conn.commit()
        return self.cursor.lastrowid, next_position
    
    def get_whatsapp_pending_requests(self, include_taken=True):
        if include_taken:
            self.cursor.execute('''
                SELECT n.*, u.username, u.first_name, u.last_name 
                FROM numbers n
                JOIN users u ON n.user_id = u.user_id
                WHERE n.status = 'pending' 
                AND n.in_queue = 1
                AND n.platform = 'whatsapp'
                ORDER BY n.queue_position ASC
            ''')
        else:
            self.cursor.execute('''
                SELECT n.*, u.username, u.first_name, u.last_name 
                FROM numbers n
                JOIN users u ON n.user_id = u.user_id
                WHERE n.status = 'pending' 
                AND n.in_queue = 1
                AND n.platform = 'whatsapp'
                AND n.taken_by IS NULL
                ORDER BY n.queue_position ASC
            ''')
        return self.cursor.fetchall()
    
    def get_max_pending_requests(self, include_taken=True):
        if include_taken:
            self.cursor.execute('''
                SELECT m.*, u.username, u.first_name, u.last_name 
                FROM max_accounts m
                JOIN users u ON m.user_id = u.user_id
                WHERE m.status IN ('pending', 'waiting_code') 
                AND m.in_queue = 1
                ORDER BY m.queue_position ASC
            ''')
        else:
            self.cursor.execute('''
                SELECT m.*, u.username, u.first_name, u.last_name 
                FROM max_accounts m
                JOIN users u ON m.user_id = u.user_id
                WHERE m.status IN ('pending', 'waiting_code') 
                AND m.in_queue = 1
                AND m.taken_by IS NULL
                ORDER BY m.queue_position ASC
            ''')
        return self.cursor.fetchall()
    
    def take_number(self, number_id, cold_id):
        self.cursor.execute('SELECT taken_by FROM numbers WHERE id = ?', (number_id,))
        result = self.cursor.fetchone()
        
        if result and result[0] is not None and result[0] != cold_id:
            return False
        
        self.cursor.execute('''
            UPDATE numbers 
            SET taken_by = ?, 
                status = 'in_progress'
            WHERE id = ? AND (taken_by IS NULL OR taken_by = ?)
        ''', (cold_id, number_id, cold_id))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def take_max_account(self, account_id, cold_id):
        self.cursor.execute('SELECT taken_by, status FROM max_accounts WHERE id = ?', (account_id,))
        result = self.cursor.fetchone()
        
        if result and result[0] is not None and result[0] != cold_id:
            return False
        
        if result and result[1] == 'pending':
            self.cursor.execute('''
                UPDATE max_accounts 
                SET taken_by = ?, 
                    status = 'in_progress'
                WHERE id = ? AND (taken_by IS NULL OR taken_by = ?)
            ''', (cold_id, account_id, cold_id))
        else:
            self.cursor.execute('''
                UPDATE max_accounts 
                SET taken_by = ?
                WHERE id = ? AND (taken_by IS NULL OR taken_by = ?)
            ''', (cold_id, account_id, cold_id))
        
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def get_number_by_id(self, number_id):
        self.cursor.execute('SELECT * FROM numbers WHERE id = ?', (number_id,))
        return self.cursor.fetchone()
    
    def get_max_account_by_id(self, account_id):
        self.cursor.execute('SELECT * FROM max_accounts WHERE id = ?', (account_id,))
        return self.cursor.fetchone()
    
    def update_number_status(self, number_id, status, **kwargs):
        query = "UPDATE numbers SET status = ?"
        values = [status]
        
        if 'code_photo_id' in kwargs:
            query += ", code_photo_id = ?"
            values.append(kwargs['code_photo_id'])
        if 'qr_photo_id' in kwargs:
            query += ", qr_photo_id = ?"
            values.append(kwargs['qr_photo_id'])
        if 'code_sent_at' in kwargs:
            query += ", code_sent_at = ?"
            values.append(kwargs['code_sent_at'])
        if 'code_entered_at' in kwargs:
            query += ", code_entered_at = ?"
            values.append(kwargs['code_entered_at'])
        if 'activated_at' in kwargs:
            query += ", activated_at = ?"
            values.append(kwargs['activated_at'])
        if 'crashed_at' in kwargs:
            query += ", crashed_at = ?"
            values.append(kwargs['crashed_at'])
        if 'total_work_time' in kwargs:
            query += ", total_work_time = ?"
            values.append(kwargs['total_work_time'])
        if 'in_queue' in kwargs:
            query += ", in_queue = ?"
            values.append(kwargs['in_queue'])
        
        query += " WHERE id = ?"
        values.append(number_id)
        
        self.cursor.execute(query, values)
        self.conn.commit()
    
    def update_max_status(self, account_id, status, **kwargs):
        query = "UPDATE max_accounts SET status = ?"
        values = [status]
        
        if 'activated_at' in kwargs:
            query += ", activated_at = ?"
            values.append(kwargs['activated_at'])
        if 'crashed_at' in kwargs:
            query += ", crashed_at = ?"
            values.append(kwargs['crashed_at'])
        if 'total_work_time' in kwargs:
            query += ", total_work_time = ?"
            values.append(kwargs['total_work_time'])
        if 'in_queue' in kwargs:
            query += ", in_queue = ?"
            values.append(kwargs['in_queue'])
        if 'taken_by' in kwargs:
            query += ", taken_by = ?"
            values.append(kwargs['taken_by'])
        if 'waiting_for_code' in kwargs:
            query += ", waiting_for_code = ?"
            values.append(kwargs['waiting_for_code'])
        if 'code_received_at' in kwargs:
            query += ", code_received_at = ?"
            values.append(kwargs['code_received_at'])
        
        query += " WHERE id = ?"
        values.append(account_id)
        
        self.cursor.execute(query, values)
        self.conn.commit()
    
    def request_max_code(self, account_id, cold_id):
        self.cursor.execute('''
            UPDATE max_accounts 
            SET status = 'waiting_code',
                waiting_for_code = 1,
                code_requested_at = ?
            WHERE id = ? AND taken_by = ?
        ''', (datetime.now(), account_id, cold_id))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def submit_max_code(self, account_id, code):
        self.cursor.execute('''
            UPDATE max_accounts 
            SET code_text = ?,
                code_received_at = ?,
                waiting_for_code = 0,
                status = 'code_received'
            WHERE id = ?
        ''', (code, datetime.now(), account_id))
        self.conn.commit()
        
        self.cursor.execute('SELECT taken_by FROM max_accounts WHERE id = ?', (account_id,))
        result = self.cursor.fetchone()
        return result[0] if result else None
    
    def request_max_extra_info(self, account_id, cold_id, extra_text):
        self.cursor.execute('''
            UPDATE max_accounts 
            SET waiting_for_extra = 1,
                extra_request = ?,
                last_extra_request = ?
            WHERE id = ? AND taken_by = ?
        ''', (extra_text, datetime.now(), account_id, cold_id))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def submit_max_extra_reply(self, account_id, reply_text):
        self.cursor.execute('''
            UPDATE max_accounts 
            SET waiting_for_extra = 0
            WHERE id = ?
        ''', (account_id,))
        self.conn.commit()
        
        self.cursor.execute('SELECT taken_by, phone_number FROM max_accounts WHERE id = ?', (account_id,))
        return self.cursor.fetchone()
    
    def remove_from_queue(self, item_id, platform='whatsapp', removed_by=None):
        if platform == 'whatsapp':
            self.cursor.execute('''
                UPDATE numbers 
                SET status = 'cancelled', in_queue = 0, taken_by = NULL
                WHERE id = ?
            ''', (item_id,))
        else:
            self.cursor.execute('''
                UPDATE max_accounts 
                SET status = 'cancelled', in_queue = 0, taken_by = NULL
                WHERE id = ?
            ''', (item_id,))
        
        self.conn.commit()
        
        if removed_by:
            self.add_log(removed_by, None, 'queue_remove', f'Removed {platform} #{item_id} from queue', platform)
    
    def add_fine(self, user_id, issued_by, amount, reason):
        self.cursor.execute('''
            INSERT INTO fines (user_id, issued_by, amount, reason, status)
            VALUES (?, ?, ?, ?, 'active')
        ''', (user_id, issued_by, amount, reason))
        
        self.cursor.execute('''
            UPDATE users 
            SET fine_amount = fine_amount + ?,
                total_fines = total_fines + ?
            WHERE user_id = ?
        ''', (amount, amount, user_id))
        
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_all_fines(self, status=None):
        query = '''
            SELECT f.*, u1.username as user_name, u2.username as issuer_name
            FROM fines f
            JOIN users u1 ON f.user_id = u1.user_id
            LEFT JOIN users u2 ON f.issued_by = u2.user_id
        '''
        params = []
        
        if status:
            query += " WHERE f.status = ?"
            params.append(status)
        
        query += " ORDER BY f.issued_date DESC"
        
        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    def reset_fine(self, fine_id, reset_by):
        self.cursor.execute('''
            UPDATE fines 
            SET status = 'paid', paid_date = ?
            WHERE id = ? AND status = 'active'
        ''', (datetime.now(), fine_id))
        
        if self.cursor.rowcount > 0:
            self.cursor.execute('SELECT user_id, amount FROM fines WHERE id = ?', (fine_id,))
            fine = self.cursor.fetchone()
            
            if fine:
                self.cursor.execute('''
                    UPDATE users 
                    SET fine_amount = fine_amount - ?
                    WHERE user_id = ?
                ''', (fine[1], fine[0]))
            
            self.conn.commit()
            return True
        
        return False
    
    def set_user_role(self, user_id, role, changed_by):
        old_role = self.get_user_role(user_id)
        self.cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
        self.conn.commit()
        self.add_log(changed_by, None, 'role_changed', f'User {user_id}: {old_role} -> {role}', 'admin')
    
    def get_user_numbers(self, user_id):
        self.cursor.execute('''
            SELECT * FROM numbers 
            WHERE user_id = ? 
            ORDER BY requested_at DESC
        ''', (user_id,))
        return self.cursor.fetchall()
    
    def get_user_max_accounts(self, user_id):
        self.cursor.execute('''
            SELECT * FROM max_accounts 
            WHERE user_id = ? 
            ORDER BY requested_at DESC
        ''', (user_id,))
        return self.cursor.fetchall()
    
    def get_active_numbers(self):
        self.cursor.execute('SELECT * FROM numbers WHERE status = "activated"')
        return self.cursor.fetchall()
    
    def get_active_max_accounts(self):
        self.cursor.execute('SELECT * FROM max_accounts WHERE status = "activated"')
        return self.cursor.fetchall()
    
    def reset_daily_stats_if_needed(self, user_id):
        today = datetime.now().date()
        self.cursor.execute('SELECT last_reset_date FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        
        if result and result[0] != today:
            self.cursor.execute('''
                UPDATE users 
                SET today_numbers = 0, 
                    today_working_time = 0, 
                    today_crashed = 0,
                    today_max_numbers = 0,
                    today_max_working_time = 0,
                    today_max_crashed = 0,
                    last_reset_date = ?
                WHERE user_id = ?
            ''', (today, user_id))
            self.conn.commit()
    
    def update_user_stats(self, user_id, action_type, platform='whatsapp'):
        self.reset_daily_stats_if_needed(user_id)
        
        if platform == 'whatsapp':
            if action_type == 'new_number':
                self.cursor.execute('''
                    UPDATE users 
                    SET total_numbers = total_numbers + 1,
                        today_numbers = today_numbers + 1
                    WHERE user_id = ?
                ''', (user_id,))
            elif action_type == 'crashed':
                self.cursor.execute('''
                    UPDATE users 
                    SET total_crashed = total_crashed + 1,
                        today_crashed = today_crashed + 1
                    WHERE user_id = ?
                ''', (user_id,))
        else:
            if action_type == 'new_number':
                self.cursor.execute('''
                    UPDATE users 
                    SET total_max_numbers = total_max_numbers + 1,
                        today_max_numbers = today_max_numbers + 1
                    WHERE user_id = ?
                ''', (user_id,))
            elif action_type == 'crashed':
                self.cursor.execute('''
                    UPDATE users 
                    SET total_max_crashed = total_max_crashed + 1,
                        today_max_crashed = today_max_crashed + 1
                    WHERE user_id = ?
                ''', (user_id,))
        
        self.conn.commit()
    
    def add_working_time(self, user_id, seconds, platform='whatsapp'):
        self.reset_daily_stats_if_needed(user_id)
        
        if platform == 'whatsapp':
            self.cursor.execute('''
                UPDATE users 
                SET total_working_time = total_working_time + ?,
                    today_working_time = today_working_time + ?
                WHERE user_id = ?
            ''', (seconds, seconds, user_id))
        else:
            self.cursor.execute('''
                UPDATE users 
                SET total_max_working_time = total_max_working_time + ?,
                    today_max_working_time = today_max_working_time + ?
                WHERE user_id = ?
            ''', (seconds, seconds, user_id))
        
        self.conn.commit()
    
    def check_referral_qualification(self, user_id):
        self.cursor.execute('''
            SELECT COUNT(*) FROM numbers WHERE user_id = ? AND status IN ('activated', 'crashed')
        ''', (user_id,))
        wa_count = self.cursor.fetchone()[0]
        
        self.cursor.execute('''
            SELECT COUNT(*) FROM max_accounts WHERE user_id = ? AND status IN ('activated', 'crashed')
        ''', (user_id,))
        max_count = self.cursor.fetchone()[0]
        
        return (wa_count + max_count) >= 2
    
    def update_referral_status(self, user_id):
        self.cursor.execute('SELECT referrer_id FROM users WHERE user_id = ? AND referred_by IS NOT NULL', (user_id,))
        result = self.cursor.fetchone()
        
        if not result:
            return False
        
        referrer_id = result[0]
        
        self.cursor.execute('''
            SELECT id, status FROM referrals 
            WHERE referrer_id = ? AND referred_id = ?
        ''', (referrer_id, user_id))
        referral = self.cursor.fetchone()
        
        if not referral or referral[1] == 'qualified':
            return False
        
        if self.check_referral_qualification(user_id):
            self.cursor.execute('''
                UPDATE referrals 
                SET status = 'qualified', qualified_date = ?
                WHERE id = ?
            ''', (datetime.now(), referral[0]))
            
            self.cursor.execute('''
                UPDATE users 
                SET qualified_referrals = qualified_referrals + 1,
                    referral_balance = referral_balance + 1,
                    total_referral_earned = total_referral_earned + 1
                WHERE user_id = ?
            ''', (referrer_id,))
            
            self.conn.commit()
            return True
        
        return False
    
    def get_referral_info(self, user_id):
        self.cursor.execute('''
            SELECT qualified_referrals, referral_balance, total_referral_earned
            FROM users WHERE user_id = ?
        ''', (user_id,))
        return self.cursor.fetchone()
    
    def get_pending_referrals(self, user_id):
        self.cursor.execute('''
            SELECT u.user_id, u.username, u.first_name, r.referred_date
            FROM referrals r
            JOIN users u ON r.referred_id = u.user_id
            WHERE r.referrer_id = ? AND r.status = 'pending'
            ORDER BY r.referred_date DESC
        ''', (user_id,))
        return self.cursor.fetchall()
    
    def get_qualified_referrals(self, user_id):
        self.cursor.execute('''
            SELECT u.user_id, u.username, u.first_name, r.qualified_date
            FROM referrals r
            JOIN users u ON r.referred_id = u.user_id
            WHERE r.referrer_id = ? AND r.status = 'qualified'
            ORDER BY r.qualified_date DESC
        ''', (user_id,))
        return self.cursor.fetchall()
    
    def get_user_stats(self, user_id):
        self.reset_daily_stats_if_needed(user_id)
        self.cursor.execute('''
            SELECT total_numbers, total_working_time, total_crashed,
                   today_numbers, today_working_time, today_crashed,
                   total_max_numbers, total_max_working_time, total_max_crashed,
                   today_max_numbers, today_max_working_time, today_max_crashed,
                   qualified_referrals, referral_balance
            FROM users WHERE user_id = ?
        ''', (user_id,))
        return self.cursor.fetchone()
    
    def get_daily_stats(self, date, platform='whatsapp'):
        if platform == 'whatsapp':
            self.cursor.execute('''
                SELECT u.user_id, u.username, u.first_name,
                       n.id, n.phone_number, n.status, 
                       n.activated_at, n.crashed_at, n.total_work_time
                FROM users u
                LEFT JOIN numbers n ON u.user_id = n.user_id AND DATE(n.requested_at) = ? AND n.platform = 'whatsapp'
                WHERE u.role IN ('user', 'cold', 'helper')
                ORDER BY u.user_id, n.requested_at
            ''', (date,))
        else:
            self.cursor.execute('''
                SELECT u.user_id, u.username, u.first_name,
                       m.id, m.phone_number, m.status, 
                       m.activated_at, m.crashed_at, m.total_work_time
                FROM users u
                LEFT JOIN max_accounts m ON u.user_id = m.user_id AND DATE(m.requested_at) = ?
                WHERE u.role IN ('user', 'cold', 'helper')
                ORDER BY u.user_id, m.requested_at
            ''', (date,))
        return self.cursor.fetchall()
    
    def get_all_users_by_role(self):
        self.cursor.execute('SELECT user_id, username, first_name, role FROM users')
        return self.cursor.fetchall()

db = Database()

# ========== ТЕКСТЫ ==========
WELCOME_TEXT = """
🌟 **Добро пожаловать в DuoDropTeam!** 🌟

**DuoDropTeam** — это лучшая команда в сфере приема аккаунтов WhatsApp и MAX!

🔹 **Мы принимаем ваши аккаунты**
🔹 **Быстрые выплаты**
🔹 **Прозрачная статистика**
🔹 **Реферальная программа**

📢 **Наша группа:** [Присоединяйся!](https://t.me/+owH-s8y7T8RmZGEy)
🤖 **Adapter:** [@DuoDrop](https://t.me/DuoDrop)
⭐ **Репутация:** [@reputatiooonnn](https://t.me/reputatiooonnn)

💰 **Реферальная программа:** Приглашай друзей и получай 1$ за каждого!
💸 **Вывод от 5$** (реферал должен сдать минимум 2 номера)

🔰 **Поддержка:** @popopep
"""

SUPPORT_TEXT = "🔰 **Поддержка DuoDropTeam:** @popopep\n\nПо всем вопросам обращайтесь к нашему саппорту."

def get_agreement_text():
    return (
        "📋 **ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ DuoDropTeam**\n\n"
        "1. **Общие положения**\n"
        "   1.1. Настоящее соглашение регулирует отношения между администрацией DuoDropTeam и пользователями сервиса.\n"
        "   1.2. Используя сервис, вы подтверждаете свое согласие с условиями данного соглашения.\n\n"
        "2. **Добровольное участие**\n"
        "   2.1. Все действия с аккаунтами WhatsApp и MAX производятся пользователями добровольно.\n"
        "   2.2. Пользователь самостоятельно несет ответственность за предоставленные номера и аккаунты.\n\n"
        "3. **Ответственность**\n"
        "   3.1. Администрация DuoDropTeam НЕ НЕСЕТ ответственности за:\n"
        "      • Блокировку или ограничение аккаунтов\n"
        "      • Потерю доступа к аккаунтам\n"
        "      • Любые последствия использования сервиса\n"
        "      • Действия третьих лиц\n\n"
        "4. **Конфиденциальность**\n"
        "   4.1. Администрация обязуется не передавать личные данные пользователей третьим лицам.\n"
        "   4.2. Номера телефонов используются только в рамках работы сервиса.\n\n"
        "5. **Правила сервиса**\n"
        "   5.1. Запрещено:\n"
        "      • Использовать сервис для противоправных действий\n"
        "      • Передавать аккаунты третьим лицам без согласования\n"
        "      • Создавать несколько аккаунтов для накрутки рефералов\n"
        "      • Оскорблять участников и администрацию\n\n"
        "6. **Штрафы и блокировки**\n"
        "   6.1. За нарушение правил могут быть применены штрафы или блокировка.\n"
        "   6.2. Решение о штрафах принимает администрация.\n\n"
        "7. **Реферальная программа**\n"
        "   7.1. Реферал засчитывается только после сдачи минимум 2 номеров (WhatsApp или MAX).\n"
        "   7.2. За каждого квалифицированного реферала начисляется 1$.\n"
        "   7.3. Вывод средств возможен от 5$.\n"
        "   7.4. Администрация имеет право аннулировать реферальный бонус при нарушении правил.\n\n"
        "8. **Заключительные положения**\n"
        "   8.1. Администрация может изменять условия соглашения без уведомления.\n"
        "   8.2. Продолжение использования сервиса означает согласие с новыми условиями.\n\n"
        "Нажимая кнопку «✅ Принимаю», вы подтверждаете, что ознакомились и согласны с условиями."
    )

def get_role_name(role):
    roles = {
        'user': 'Пользователь',
        'cold': 'Холодка',
        'helper': 'Помощник',
        'owner': 'Владелец'
    }
    return roles.get(role, 'Пользователь')

def get_user_keyboard():
    keyboard = [
        [KeyboardButton("📱 WhatsApp"), KeyboardButton("📲 MAX")],
        [KeyboardButton("📊 Моя статистика"), KeyboardButton("👤 Профиль")],
        [KeyboardButton("💰 Рефералы"), KeyboardButton("🔰 Поддержка")],
        [KeyboardButton("🔄 Проверить очередь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cold_keyboard():
    keyboard = [
        [KeyboardButton("🆕 Запросить WhatsApp"), KeyboardButton("🆕 Запросить MAX")],
        [KeyboardButton("📋 WhatsApp очередь"), KeyboardButton("📋 MAX очередь")],
        [KeyboardButton("📋 Мои WhatsApp"), KeyboardButton("📋 Мои MAX")],
        [KeyboardButton("📊 Моя статистика"), KeyboardButton("👤 Профиль")],
        [KeyboardButton("💰 Рефералы"), KeyboardButton("🔰 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_helper_keyboard():
    keyboard = [
        [KeyboardButton("📊 WhatsApp статистика"), KeyboardButton("📊 MAX статистика")],
        [KeyboardButton("📋 Все WhatsApp"), KeyboardButton("📋 Все MAX")],
        [KeyboardButton("🗑 Удалить из очереди")],
        [KeyboardButton("📱 WhatsApp"), KeyboardButton("📲 MAX")],
        [KeyboardButton("📊 Моя статистика"), KeyboardButton("👤 Профиль")],
        [KeyboardButton("💰 Рефералы"), KeyboardButton("🔰 Поддержка")],
        [KeyboardButton("🔄 Проверить очередь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_owner_keyboard():
    keyboard = [
        [KeyboardButton("📊 WhatsApp статистика"), KeyboardButton("📊 MAX статистика")],
        [KeyboardButton("📋 Все WhatsApp"), KeyboardButton("📋 Все MAX")],
        [KeyboardButton("👥 Управление ролями"), KeyboardButton("⚖️ Штрафы")],
        [KeyboardButton("📋 Логи"), KeyboardButton("🗑 Удалить из очереди")],
        [KeyboardButton("📱 WhatsApp"), KeyboardButton("📲 MAX")],
        [KeyboardButton("📊 Моя статистика"), KeyboardButton("👤 Профиль")],
        [KeyboardButton("💰 Рефералы"), KeyboardButton("🔰 Поддержка")],
        [KeyboardButton("🔄 Проверить очередь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_type_selection_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📝 Обычный код", callback_data="type_code"),
            InlineKeyboardButton("📷 QR код", callback_data="type_qr")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_whatsapp_action_keyboard(number_id, request_type, taken_by=None):
    buttons = []
    
    if taken_by is None:
        if request_type == 'qr':
            buttons.append(InlineKeyboardButton("📷 Взять и отправить QR", callback_data=f"wa_take_qr_{number_id}"))
        else:
            buttons.append(InlineKeyboardButton("📝 Взять и отправить код", callback_data=f"wa_take_code_{number_id}"))
    else:
        if request_type == 'qr':
            buttons.append(InlineKeyboardButton("📷 Отправить QR", callback_data=f"wa_send_qr_{number_id}"))
        else:
            buttons.append(InlineKeyboardButton("📝 Отправить код", callback_data=f"wa_send_code_{number_id}"))
    
    return InlineKeyboardMarkup([buttons])

def get_max_action_keyboard(account_id, taken_by=None, status=None):
    buttons = []
    
    if taken_by is None:
        buttons.append(InlineKeyboardButton("📲 Взять аккаунт", callback_data=f"max_take_{account_id}"))
    else:
        if status == 'in_progress':
            buttons.append(InlineKeyboardButton("🔑 Запросить код", callback_data=f"max_request_code_{account_id}"))
        if status in ['in_progress', 'code_received']:
            buttons.append(InlineKeyboardButton("📝 Запросить доп инфо", callback_data=f"max_request_extra_{account_id}"))
        buttons.append(InlineKeyboardButton("✅ Активирован", callback_data=f"max_activated_{account_id}"))
        buttons.append(InlineKeyboardButton("❌ Не встал", callback_data=f"max_failed_{account_id}"))
        if status == 'activated':
            buttons.append(InlineKeyboardButton("💥 Слетел", callback_data=f"max_crashed_{account_id}"))
    
    keyboard = []
    for i in range(0, len(buttons), 2):
        keyboard.append(buttons[i:i+2])
    
    return InlineKeyboardMarkup(keyboard)

def get_code_action_keyboard(number_id):
    keyboard = [
        [
            InlineKeyboardButton("✅ Номер встал", callback_data=f"activated_{number_id}"),
            InlineKeyboardButton("❌ Номер не встал", callback_data=f"failed_{number_id}")
        ],
        [InlineKeyboardButton("💥 Номер слетел", callback_data=f"crashed_{number_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_queue_check_keyboard(item_id, platform='whatsapp'):
    data_prefix = "wa_queue" if platform == 'whatsapp' else "max_queue"
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, оставить", callback_data=f"{data_prefix}_keep_{item_id}"),
            InlineKeyboardButton("❌ Нет, убрать", callback_data=f"{data_prefix}_remove_{item_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_retry_keyboard(number_id):
    keyboard = [
        [
            InlineKeyboardButton("🔄 Повторить с этим номером", callback_data=f"retry_{number_id}"),
            InlineKeyboardButton("❌ Отменить номер", callback_data=f"cancel_number_{number_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
def start(update: Update, context: CallbackContext):
    user = update.effective_user
user = update.effective_user
    # ВРЕМЕННЫЙ КОД ДЛЯ НАЗНАЧЕНИЯ ВЛАДЕЛЬЦА
    if user.id == 7787440009:  # ВСТАВЬ СВОЙ ID СЮДА!
        db.cursor.execute("UPDATE users SET role = 'owner' WHERE user_id = ?", (user.id,))
        db.conn.commit()
    
    referrer_id = None
    if context.args and len(context.args) > 0:
        try:
            referrer_id = int(context.args[0])
        except:
            pass
    
    db.add_user(user.id, user.username, user.first_name, user.last_name, referrer_id)
    
    if not db.check_agreement(user.id):
        agreement_text = get_agreement_text()
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Принимаю", callback_data="accept_agreement")
        ]])
        update.message.reply_text(
            agreement_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        return WAITING_FOR_AGREEMENT
    
    role = db.get_user_role(user.id)
    
    welcome_with_buttons = WELCOME_TEXT + f"\n\n👋 Привет, {user.first_name}! Твой статус: {get_role_name(role)}"
    
    if role == 'owner':
        keyboard = get_owner_keyboard()
    elif role == 'helper':
        keyboard = get_helper_keyboard()
    elif role == 'cold':
        keyboard = get_cold_keyboard()
    else:
        keyboard = get_user_keyboard()
    
    update.message.reply_text(
        welcome_with_buttons,
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=keyboard
    )
    
    db.add_log(user.id, user.username, 'user_start', 'Started bot', 'auth')

def handle_agreement(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "accept_agreement":
        db.accept_agreement(user_id)
        
        query.edit_message_text(
            "✅ Спасибо! Вы приняли пользовательское соглашение.\n\n"
            "Теперь вы можете пользоваться ботом.",
            parse_mode='Markdown'
        )
        
        role = db.get_user_role(user_id)
        welcome_with_buttons = WELCOME_TEXT + f"\n\n👋 Привет, {query.from_user.first_name}! Твой статус: {get_role_name(role)}"
        
        if role == 'owner':
            keyboard = get_owner_keyboard()
        elif role == 'helper':
            keyboard = get_helper_keyboard()
        elif role == 'cold':
            keyboard = get_cold_keyboard()
        else:
            keyboard = get_user_keyboard()
        
        context.bot.send_message(
            chat_id=user_id,
            text=welcome_with_buttons,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
    
    return ConversationHandler.END

def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username
    role = db.get_user_role(user_id)
    
    if not db.check_agreement(user_id) and text != '/start':
        agreement_text = get_agreement_text()
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Принимаю", callback_data="accept_agreement")
        ]])
        update.message.reply_text(
            agreement_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        return WAITING_FOR_AGREEMENT
    
    if text == "🔰 Поддержка":
        update.message.reply_text(SUPPORT_TEXT, parse_mode='Markdown')
        db.add_log(user_id, username, 'support_click', 'Clicked support button', 'navigation')
    
    elif text == "💰 Рефералы":
        show_referral_info(update, context, user_id)
    
    elif text == "👤 Профиль":
        show_profile(update, context, user_id)
    
    elif text == "📊 Моя статистика":
        generate_user_report(update, context, user_id)
    
    elif text == "🔄 Проверить очередь":
        check_user_queue(update, context, user_id)
    
    elif text == "📱 WhatsApp":
        update.message.reply_text(
            "📞 Введите номер телефона для WhatsApp в международном формате (например: 79123456789):"
        )
        return WAITING_FOR_NUMBER
    
    elif text == "📲 MAX":
        update.message.reply_text(
            "📞 Введите номер телефона для MAX в международном формате (например: 79123456789):"
        )
        return WAITING_FOR_MAX_NUMBER
    
    elif role == 'cold':
        if text == "🆕 Запросить WhatsApp":
            group_id = db.get_group_id()
            if not group_id:
                update.message.reply_text("❌ Группа не настроена! Обратитесь к администратору.")
                return
            
            context.bot.send_message(
                chat_id=group_id,
                text="🆕 Требуется номер WhatsApp!\nНажмите '📱 WhatsApp' чтобы предоставить номер."
            )
            update.message.reply_text("✅ Запрос на WhatsApp отправлен в группу!")
            db.add_log(user_id, username, 'whatsapp_requested', 'Requested WhatsApp in group', 'whatsapp')
        
        elif text == "🆕 Запросить MAX":
            group_id = db.get_group_id()
            if not group_id:
                update.message.reply_text("❌ Группа не настроена! Обратитесь к администратору.")
                return
            
            context.bot.send_message(
                chat_id=group_id,
                text="🆕 Требуется номер MAX!\nНажмите '📲 MAX' чтобы предоставить номер."
            )
            update.message.reply_text("✅ Запрос на MAX отправлен в группу!")
            db.add_log(user_id, username, 'max_requested', 'Requested MAX in group', 'max')
        
        elif text == "📋 WhatsApp очередь":
            show_whatsapp_queue(update, context)
        
        elif text == "📋 MAX очередь":
            show_max_queue(update, context)
        
        elif text == "📋 Мои WhatsApp":
            show_my_whatsapp(update, context, user_id)
        
        elif text == "📋 Мои MAX":
            show_my_max(update, context, user_id)
    
    elif role == 'helper':
        if text == "📊 WhatsApp статистика":
            generate_whatsapp_daily_stats(update, context)
        
        elif text == "📊 MAX статистика":
            generate_max_daily_stats(update, context)
        
        elif text == "📋 Все WhatsApp":
            show_all_whatsapp_queue(update, context)
        
        elif text == "📋 Все MAX":
            show_all_max_queue(update, context)
        
        elif text == "🗑 Удалить из очереди":
            update.message.reply_text(
                "Введите ID номера и платформу (whatsapp/max) для удаления из очереди.\n"
                "Формат: ID платформа\n"
                "Пример: 123 whatsapp"
            )
            return WAITING_FOR_QUEUE_REMOVE
    
    elif role == 'owner':
        if text == "📊 WhatsApp статистика":
            generate_whatsapp_daily_stats(update, context)
        
        elif text == "📊 MAX статистика":
            generate_max_daily_stats(update, context)
        
        elif text == "📋 Все WhatsApp":
            show_all_whatsapp_queue(update, context)
        
        elif text == "📋 Все MAX":
            show_all_max_queue(update, context)
        
        elif text == "👥 Управление ролями":
            show_role_management(update, context)
        
        elif text == "📋 Логи":
            show_logs(update, context)
        
        elif text == "⚖️ Штрафы":
            show_fines_menu(update, context)
        
        elif text == "🗑 Удалить из очереди":
            update.message.reply_text(
                "Введите ID номера и платформу (whatsapp/max) для удаления из очереди.\n"
                "Формат: ID платформа\n"
                "Пример: 123 whatsapp"
            )
            return WAITING_FOR_QUEUE_REMOVE

def handle_whatsapp_number_input(update: Update, context: CallbackContext):
    phone_number = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not phone_number.isdigit() or len(phone_number) < 10:
        update.message.reply_text(
            "❌ Неверный формат номера. Попробуйте снова:",
            reply_markup=get_user_keyboard()
        )
        return ConversationHandler.END
    
    context.user_data['temp_phone'] = phone_number
    context.user_data['platform'] = 'whatsapp'
    
    update.message.reply_text(
        "📱 Выберите тип получения кода для WhatsApp:",
        reply_markup=get_type_selection_keyboard()
    )
    return WAITING_FOR_TYPE

def handle_max_number_input(update: Update, context: CallbackContext):
    phone_number = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not phone_number.isdigit() or len(phone_number) < 10:
        update.message.reply_text(
            "❌ Неверный формат номера. Попробуйте снова:",
            reply_markup=get_user_keyboard()
        )
        return ConversationHandler.END
    
    account_id, queue_pos = db.create_max_request(user_id, phone_number)
    db.update_user_stats(user_id, 'new_number', platform='max')
    
    cold_staff = db.get_all_cold_staff()
    for cold_id in cold_staff:
        try:
            context.bot.send_message(
                chat_id=cold_id,
                text=f"📲 Новая MAX заявка #{account_id} (Позиция: {queue_pos})\n"
                     f"📞 Номер: {phone_number}\n"
                     f"👤 От: @{update.effective_user.username or 'нет username'}\n"
                     f"Нажмите '📋 MAX очередь' для просмотра."
            )
        except:
            pass
    
    update.message.reply_text(
        f"✅ Номер для MAX принят! Ваша позиция в очереди: {queue_pos}\n"
        f"Ожидайте, когда холодка начнет вход в аккаунт.",
        reply_markup=get_user_keyboard()
    )
    
    return ConversationHandler.END

def handle_type_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    selection = query.data
    user_id = query.from_user.id
    phone_number = context.user_data.get('temp_phone')
    platform = context.user_data.get('platform', 'whatsapp')
    
    if selection == "type_code":
        request_type = 'code'
        type_text = "обычный код"
    else:
        request_type = 'qr'
        type_text = "QR код"
    
    if platform == 'whatsapp':
        number_id, queue_pos = db.create_whatsapp_request(user_id, phone_number, request_type)
        db.update_user_stats(user_id, 'new_number', platform='whatsapp')
        
        cold_staff = db.get_all_cold_staff()
        for cold_id in cold_staff:
            try:
                context.bot.send_message(
                    chat_id=cold_id,
                    text=f"📱 Новая WhatsApp заявка #{number_id} (Позиция: {queue_pos})\n"
                         f"📞 Номер: {phone_number}\n"
                         f"📋 Тип: {type_text}\n"
                         f"👤 От: @{query.from_user.username or 'нет username'}\n"
                         f"Нажмите '📋 WhatsApp очередь' для просмотра."
                )
            except:
                pass
        
        query.edit_message_text(
            f"✅ Номер для WhatsApp принят! Ваша позиция в очереди: {queue_pos}\n"
            f"Ожидайте {type_text} от Холодки.",
            reply_markup=None
        )
    
    context.user_data.pop('temp_phone', None)
    context.user_data.pop('platform', None)
    return ConversationHandler.END

def show_whatsapp_queue(update: Update, context: CallbackContext):
    pending = db.get_whatsapp_pending_requests(include_taken=False)
    
    if not pending:
        update.message.reply_text("📭 Нет свободных WhatsApp номеров в очереди.")
        return
    
    for req in pending[:5]:
        type_emoji = "📝" if req[12] == 'code' else "📷"
        type_text = "обычный код" if req[12] == 'code' else "QR код"
        
        msg = (
            f"{type_emoji} WhatsApp #{req[0]} (Поз.{req[14]})\n"
            f"📞 Номер: {req[1]}\n"
            f"👤 От: @{req[16] or 'нет username'}\n"
            f"⏰ Запрошен: {req[4]}\n"
            f"📋 Тип: {type_text}\n"
        )
        update.message.reply_text(
            msg,
            reply_markup=get_whatsapp_action_keyboard(req[0], req[12], None)
        )

def show_max_queue(update: Update, context: CallbackContext):
    pending = db.get_max_pending_requests(include_taken=False)
    
    if not pending:
        update.message.reply_text("📭 Нет свободных MAX аккаунтов в очереди.")
        return
    
    for req in pending[:5]:
        status_text = {
            'pending': '⏳ В очереди',
            'waiting_code': '🔑 Ожидает код',
        }.get(req[3], req[3])
        
        msg = (
            f"📲 MAX #{req[0]} (Поз.{req[13]})\n"
            f"📞 Номер: {req[1]}\n"
            f"👤 От: @{req[16] or 'нет username'}\n"
            f"⏰ Запрошен: {req[4]}\n"
            f"📊 Статус: {status_text}\n"
        )
        update.message.reply_text(
            msg,
            reply_markup=get_max_action_keyboard(req[0], None, req[3])
        )

def show_my_whatsapp(update: Update, context: CallbackContext, cold_id):
    db.cursor.execute('''
        SELECT n.*, u.username 
        FROM numbers n
        JOIN users u ON n.user_id = u.user_id
        WHERE n.taken_by = ? AND n.platform = 'whatsapp'
        ORDER BY n.requested_at DESC
    ''', (cold_id,))
    
    numbers = db.cursor.fetchall()
    
    if not numbers:
        update.message.reply_text("📭 У вас нет активных WhatsApp номеров.")
        return
    
    for num in numbers[:5]:
        status_text = {
            'in_progress': '⏳ Ожидает кода',
            'code_sent': '🔑 Код отправлен',
            'code_entered': '✅ Код введен',
            'activated': '✅ Активен',
            'crashed': '💥 Слетел'
        }.get(num[3], num[3])
        
        msg = (
            f"📱 WhatsApp #{num[0]}\n"
            f"📞 Номер: {num[1]}\n"
            f"👤 Пользователь: @{num[16]}\n"
            f"📊 Статус: {status_text}"
        )
        update.message.reply_text(msg)

def show_my_max(update: Update, context: CallbackContext, cold_id):
    db.cursor.execute('''
        SELECT m.*, u.username 
        FROM max_accounts m
        JOIN users u ON m.user_id = u.user_id
        WHERE m.taken_by = ?
        ORDER BY m.requested_at DESC
    ''', (cold_id,))
    
    accounts = db.cursor.fetchall()
    
    if not accounts:
        update.message.reply_text("📭 У вас нет активных MAX аккаунтов.")
        return
    
    for acc in accounts[:5]:
        status_text = {
            'in_progress': '⏳ В работе',
            'waiting_code': '🔑 Ожидает код',
            'code_received': '✅ Код получен',
            'activated': '✅ Активен',
            'crashed': '💥 Слетел'
        }.get(acc[3], acc[3])
        
        msg = (
            f"📲 MAX #{acc[0]}\n"
            f"📞 Номер: {acc[1]}\n"
            f"👤 Пользователь: @{acc[16]}\n"
            f"📊 Статус: {status_text}"
        )
        update.message.reply_text(msg)

def show_all_whatsapp_queue(update: Update, context: CallbackContext):
    pending = db.get_whatsapp_pending_requests(include_taken=True)
    
    if not pending:
        update.message.reply_text("📭 WhatsApp очередь пуста.")
        return
    
    msg = "📋 **Вся WhatsApp очередь:**\n\n"
    for req in pending:
        type_emoji = "📝" if req[12] == 'code' else "📷"
        taken_by = "🆓" if req[13] is None else f"👤 {req[13]}"
        msg += f"{type_emoji} #{req[0]} (Поз.{req[14]}) {req[1]} - {taken_by}\n"
    
    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            update.message.reply_text(msg[i:i+4000], parse_mode='Markdown')
    else:
        update.message.reply_text(msg, parse_mode='Markdown')

def show_all_max_queue(update: Update, context: CallbackContext):
    pending = db.get_max_pending_requests(include_taken=True)
    
    if not pending:
        update.message.reply_text("📭 MAX очередь пуста.")
        return
    
    msg = "📋 **Вся MAX очередь:**\n\n"
    for req in pending:
        taken_by = "🆓" if req[14] is None else f"👤 {req[14]}"
        status = "⏳" if req[3] == 'pending' else "🔑" if req[3] == 'waiting_code' else "🔄"
        msg += f"{status} #{req[0]} (Поз.{req[13]}) {req[1]} - {taken_by}\n"
    
    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            update.message.reply_text(msg[i:i+4000], parse_mode='Markdown')
    else:
        update.message.reply_text(msg, parse_mode='Markdown')

def handle_queue_remove(update: Update, context: CallbackContext):
    try:
        text = update.message.text.strip().split()
        if len(text) != 2:
            raise ValueError
        
        item_id = int(text[0])
        platform = text[1].lower()
        
        if platform not in ['whatsapp', 'max']:
            raise ValueError
        
        db.remove_from_queue(item_id, platform, update.effective_user.id)
        update.message.reply_text(f"✅ {platform} #{item_id} удален из очереди!")
        
    except:
        update.message.reply_text(
            "❌ Неверный формат. Используйте: ID платформа\n"
            "Пример: 123 whatsapp"
        )
    
    return ConversationHandler.END

def show_referral_info(update: Update, context: CallbackContext, user_id):
    info = db.get_referral_info(user_id)
    if not info:
        update.message.reply_text("❌ Ошибка получения информации.")
        return
    
    qualified, balance, total = info
    
    pending = db.get_pending_referrals(user_id)
    qualified_list = db.get_qualified_referrals(user_id)
    
    text = (
        f"💰 **Реферальная программа DuoDropTeam**\n\n"
        f"👥 **Квалифицированные рефералы:** {qualified}\n"
        f"💵 **Текущий баланс:** ${balance:.2f}\n"
        f"📊 **Всего заработано:** ${total:.2f}\n\n"
        f"**Условия:**\n"
        f"• Реферал засчитывается только после сдачи 2+ номеров\n"
        f"• За каждого квалифицированного реферала +1$\n"
        f"• Минимальная сумма для вывода: 5$\n"
        f"• Для вывода напишите @popopep\n\n"
    )
    
    if balance >= 5:
        text += f"✅ **Вы можете вывести ${balance:.2f}!**\n"
        text += f"Напишите @popopep для получения выплаты.\n\n"
    else:
        need = 5 - balance
        text += f"⏳ **До вывода осталось: ${need:.2f}**\n\n"
    
    if pending:
        text += f"**Ожидают квалификации ({len(pending)}):**\n"
        for ref in pending[:5]:
            date = datetime.strptime(ref[3], '%Y-%m-%d %H:%M:%S.%f').strftime('%d.%m.%Y')
            username = f"@{ref[1]}" if ref[1] else ref[2]
            text += f"• {username} - {date}\n"
        text += "\n"
    
    if qualified_list:
        text += f"**Квалифицированные ({len(qualified_list)}):**\n"
        for ref in qualified_list[:5]:
            date = datetime.strptime(ref[3], '%Y-%m-%d %H:%M:%S.%f').strftime('%d.%m.%Y')
            username = f"@{ref[1]}" if ref[1] else ref[2]
            text += f"• {username} - {date}\n"
        text += "\n"
    
    bot_username = context.bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    text += f"**Ваша реферальная ссылка:**\n`{ref_link}`"
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить", callback_data="refresh_referral")
    ]])
    
    update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

def show_fines_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("📋 Все штрафы", callback_data="fines_list_all")],
        [InlineKeyboardButton("➕ Наложить штраф", callback_data="fines_add")],
        [InlineKeyboardButton("✅ Обнулить штраф", callback_data="fines_reset")]
    ]
    
    update.message.reply_text(
        "⚖️ **Управление штрафами**\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def show_role_management(update: Update, context: CallbackContext):
    users = db.get_all_users_by_role()
    
    text = "👥 **Управление ролями пользователей**\n\n"
    
    roles = {'owner': [], 'helper': [], 'cold': [], 'user': []}
    for user in users:
        user_id, username, first_name, role = user
        roles[role].append(f"@{username or first_name} (ID: {user_id})")
    
    text += "**Владельцы:**\n" + "\n".join(roles['owner'][:5]) + "\n\n"
    text += "**Помощники:**\n" + "\n".join(roles['helper'][:5]) + "\n\n"
    text += "**Холодка:**\n" + "\n".join(roles['cold'][:5]) + "\n\n"
    text += "**Пользователи:** " + str(len(roles['user'])) + "\n\n"
    
    text += "**Изменить роль:**\n"
    text += "Формат: `роль user_id`\n"
    text += "Пример: `helper 123456789`\n"
    text += "Роли: owner, helper, cold, user"
    
    update.message.reply_text(text, parse_mode='Markdown')
    return WAITING_FOR_ROLE_CHANGE

def handle_role_change(update: Update, context: CallbackContext):
    try:
        text = update.message.text.strip().split()
        if len(text) != 2:
            raise ValueError
        
        role = text[0].lower()
        user_id = int(text[1])
        
        if role not in ['owner', 'helper', 'cold', 'user']:
            raise ValueError
        
        db.set_user_role(user_id, role, update.effective_user.id)
        update.message.reply_text(f"✅ Роль пользователя {user_id} изменена на {role}!")
        
    except:
        update.message.reply_text(
            "❌ Неверный формат. Используйте: роль user_id\n"
            "Пример: helper 123456789"
        )
    
    return ConversationHandler.END

def show_logs(update: Update, context: CallbackContext):
    logs = db.get_logs(days=3)
    
    if not logs:
        update.message.reply_text("📋 Логов за последние 3 дня нет.")
        return
    
    text = "📋 **Последние логи (3 дня):**\n\n"
    
    for log in logs[:30]:
        log_id, user_id, username, action, details, platform, timestamp = log
        time_str = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f').strftime('%d.%m %H:%M')
        text += f"[{time_str}] @{username or user_id}: {action} - {details} ({platform})\n"
    
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            update.message.reply_text(text[i:i+4000], parse_mode='Markdown')
    else:
        update.message.reply_text(text, parse_mode='Markdown')

def check_user_queue(update: Update, context: CallbackContext, user_id):
    db.cursor.execute('''
        SELECT phone_number, queue_position, platform
        FROM numbers 
        WHERE user_id = ? AND status = 'pending' AND in_queue = 1
        UNION
        SELECT phone_number, queue_position, 'max' as platform
        FROM max_accounts 
        WHERE user_id = ? AND status = 'pending' AND in_queue = 1
        ORDER BY queue_position
    ''', (user_id, user_id))
    
    numbers = db.cursor.fetchall()
    
    if not numbers:
        update.message.reply_text("📭 У вас нет номеров в очереди.")
        return
    
    msg = "📊 **Ваша очередь:**\n\n"
    for num in numbers:
        platform_emoji = "📱" if num[2] == 'whatsapp' else "📲"
        msg += f"{platform_emoji} {num[0]} - позиция {num[1]}\n"
    
    update.message.reply_text(msg, parse_mode='Markdown')

def show_profile(update: Update, context: CallbackContext, user_id):
    stats = db.get_user_stats(user_id)
    
    if not stats:
        update.message.reply_text("❌ Ошибка получения статистики.")
        return
    
    (wa_total, wa_time, wa_crashed, wa_today, wa_today_time, wa_today_crashed,
     max_total, max_time, max_crashed, max_today, max_today_time, max_today_crashed,
     referrals, ref_balance) = stats
    
    def format_time(seconds):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        days = hours // 24
        hours = hours % 24
        return f"{days}д {hours}ч {minutes}мин" if days > 0 else f"{hours}ч {minutes}мин"
    
    text = (
        f"👤 **Профиль пользователя**\n\n"
        f"💰 **Реферальный баланс:** ${ref_balance:.2f}\n"
        f"👥 **Рефералов:** {referrals}\n\n"
        f"📱 **WhatsApp:**\n"
        f"   За все время: {wa_total} номеров, {format_time(wa_time)}, слетело {wa_crashed}\n"
        f"   За сегодня: {wa_today} номеров, {format_time(wa_today_time)}, слетело {wa_today_crashed}\n\n"
        f"📲 **MAX:**\n"
        f"   За все время: {max_total} аккаунтов, {format_time(max_time)}, слетело {max_crashed}\n"
        f"   За сегодня: {max_today} аккаунтов, {format_time(max_today_time)}, слетело {max_today_crashed}\n"
    )
    
    update.message.reply_text(text, parse_mode='Markdown')

def generate_user_report(update: Update, context: CallbackContext, user_id):
    wa_numbers = db.get_user_numbers(user_id)
    max_accounts = db.get_user_max_accounts(user_id)
    
    if not wa_numbers and not max_accounts:
        update.message.reply_text("📭 У вас пока нет аккаунтов.")
        return
    
    report = "📊 **Отчет по аккаунтам:**\n\n"
    
    if wa_numbers:
        report += "📱 **WhatsApp:**\n"
        for num in wa_numbers[:10]:
            status_emoji = {
                'pending': '⏳', 'in_progress': '🔄', 'code_sent': '🔑',
                'code_entered': '✅', 'activated': '✅', 'crashed': '💥',
                'failed': '❌', 'cancelled': '🚫'
            }.get(num[3], '❓')
            
            report += f"{status_emoji} {num[1]}\n"
            if num[7]:
                activated = datetime.strptime(num[7], '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')
                report += f"   ✅ Встал: {activated}\n"
            if num[8]:
                crashed = datetime.strptime(num[8], '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')
                report += f"   💥 Слетел: {crashed}\n"
            if num[9]:
                hours = num[9] // 3600
                minutes = (num[9] % 3600) // 60
                days = hours // 24
                hours = hours % 24
                time_str = f"{days}д {hours}ч {minutes}мин" if days > 0 else f"{hours}ч {minutes}мин"
                report += f"   ⏱ Отстоял: {time_str}\n"
            report += "\n"
    
    if max_accounts:
        report += "📲 **MAX:**\n"
        for acc in max_accounts[:10]:
            status_emoji = {
                'pending': '⏳', 'waiting_code': '🔑', 'code_received': '✅',
                'in_progress': '🔄', 'activated': '✅', 'crashed': '💥',
                'failed': '❌', 'cancelled': '🚫'
            }.get(acc[3], '❓')
            
            report += f"{status_emoji} {acc[1]}\n"
            if acc[7]:
                activated = datetime.strptime(acc[7], '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')
                report += f"   ✅ Активирован: {activated}\n"
            if acc[8]:
                crashed = datetime.strptime(acc[8], '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')
                report += f"   💥 Слетел: {crashed}\n"
            if acc[9]:
                hours = acc[9] // 3600
                minutes = (acc[9] % 3600) // 60
                days = hours // 24
                hours = hours % 24
                time_str = f"{days}д {hours}ч {minutes}мин" if days > 0 else f"{hours}ч {minutes}мин"
                report += f"   ⏱ Проработал: {time_str}\n"
            report += "\n"
    
    if len(report) > 4000:
        for i in range(0, len(report), 4000):
            update.message.reply_text(report[i:i+4000], parse_mode='Markdown')
    else:
        update.message.reply_text(report, parse_mode='Markdown')

def generate_whatsapp_daily_stats(update: Update, context: CallbackContext):
    today = datetime.now().date()
    stats = db.get_daily_stats(today, 'whatsapp')
    
    if not stats:
        update.message.reply_text("📊 За сегодня нет данных по WhatsApp.")
        return
    
    report = f"📊 **WhatsApp статистика за {today}**\n\n"
    current_user = None
    
    for row in stats:
        user_id, username, first_name, num_id, phone, status, activated, crashed, work_time = row
        
        if current_user != user_id:
            if current_user is not None:
                report += "\n"
            current_user = user_id
            report += f"👤 @{username or first_name} (ID: {user_id}):\n"
        
        if num_id:
            status_emoji = {
                'activated': '✅', 'crashed': '💥', 'failed': '❌', 'cancelled': '🚫'
            }.get(status, '⏳')
            
            time_str = ""
            if work_time:
                hours = work_time // 3600
                minutes = (work_time % 3600) // 60
                days = hours // 24
                hours = hours % 24
                time_str = f"{days}д {hours}ч {minutes}мин" if days > 0 else f"{hours}ч {minutes}мин"
            
            activated_str = datetime.strptime(activated, '%Y-%m-%d %H:%M:%S.%f').strftime('%H:%M') if activated else '-'
            crashed_str = datetime.strptime(crashed, '%Y-%m-%d %H:%M:%S.%f').strftime('%H:%M') if crashed else '-'
            
            report += f"   {status_emoji} {phone}\n"
            report += f"      ✅ Встал: {activated_str}\n"
            report += f"      💥 Слетел: {crashed_str}\n"
            report += f"      ⏱ Простоял: {time_str}\n"
    
    if len(report) > 4000:
        for i in range(0, len(report), 4000):
            update.message.reply_text(report[i:i+4000], parse_mode='Markdown')
    else:
        update.message.reply_text(report, parse_mode='Markdown')

def generate_max_daily_stats(update: Update, context: CallbackContext):
    today = datetime.now().date()
    stats = db.get_daily_stats(today, 'max')
    
    if not stats:
        update.message.reply_text("📊 За сегодня нет данных по MAX.")
        return
    
    report = f"📊 **MAX статистика за {today}**\n\n"
    current_user = None
    
    for row in stats:
        user_id, username, first_name, acc_id, phone, status, activated, crashed, work_time = row
        
        if current_user != user_id:
            if current_user is not None:
                report += "\n"
            current_user = user_id
            report += f"👤 @{username or first_name} (ID: {user_id}):\n"
        
        if acc_id:
            status_emoji = {
                'activated': '✅', 'crashed': '💥', 'failed': '❌', 'cancelled': '🚫'
            }.get(status, '⏳')
            
            time_str = ""
            if work_time:
                hours = work_time // 3600
                minutes = (work_time % 3600) // 60
                days = hours // 24
                hours = hours % 24
                time_str = f"{days}д {hours}ч {minutes}мин" if days > 0 else f"{hours}ч {minutes}мин"
            
            activated_str = datetime.strptime(activated, '%Y-%m-%d %H:%M:%S.%f').strftime('%H:%M') if activated else '-'
            crashed_str = datetime.strptime(crashed, '%Y-%m-%d %H:%M:%S.%f').strftime('%H:%M') if crashed else '-'
            
            report += f"   {status_emoji} {phone}\n"
            report += f"      ✅ Активирован: {activated_str}\n"
            report += f"      💥 Слетел: {crashed_str}\n"
            report += f"      ⏱ Проработал: {time_str}\n"
    
    if len(report) > 4000:
        for i in range(0, len(report), 4000):
            update.message.reply_text(report[i:i+4000], parse_mode='Markdown')
    else:
        update.message.reply_text(report, parse_mode='Markdown')

def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    data = query.data
    user_id = query.from_user.id
    role = db.get_user_role(user_id)
    
    if data == "refresh_referral":
        show_referral_info(update, context, user_id)
    
    elif data == "fines_list_all":
        fines = db.get_all_fines()
        
        if not fines:
            query.edit_message_text("📋 Нет штрафов.")
            return
        
        text = "📋 **Все штрафы:**\n\n"
        for fine in fines[:10]:
            text += f"ID: {fine[0]}\n"
            text += f"👤 Пользователь: @{fine[11] or fine[10]}\n"
            text += f"💰 Сумма: ${fine[3]}\n"
            text += f"📝 Причина: {fine[4]}\n"
            text += f"📅 Дата: {fine[5]}\n"
            text += f"👮 Выдал: @{fine[12]}\n"
            text += f"📊 Статус: {fine[6]}\n\n"
        
        query.edit_message_text(text, parse_mode='Markdown')
    
    elif data == "fines_add":
        query.edit_message_text(
            "Введите ID пользователя, на которого хотите наложить штраф:"
        )
        return WAITING_FOR_FINE_USER
    
    elif data == "fines_reset":
        query.edit_message_text(
            "Введите ID штрафа, который хотите обнулить:"
        )
        return WAITING_FOR_FINE_RESET
    
    elif data.startswith('wa_take_qr_') or data.startswith('wa_take_code_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав для этого действия.")
            return
        
        is_qr = 'qr' in data
        number_id = int(data.split('_')[3])
        
        if db.take_number(number_id, user_id):
            context.user_data['current_number_id'] = number_id
            
            if is_qr:
                query.edit_message_text(
                    "📷 Отправьте **фото с QR кодом** для WhatsApp.\n"
                    "Убедитесь, что QR код хорошо видно.",
                    parse_mode='Markdown'
                )
                return WAITING_FOR_QR_PHOTO
            else:
                query.edit_message_text(
                    "📷 Отправьте **фото с кодом** для WhatsApp.\n"
                    "Убедитесь, что код хорошо видно.",
                    parse_mode='Markdown'
                )
                return WAITING_FOR_CODE_PHOTO
        else:
            query.edit_message_text("❌ Этот номер уже взят другим.")
    
    elif data.startswith('wa_send_qr_') or data.startswith('wa_send_code_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        is_qr = 'qr' in data
        number_id = int(data.split('_')[3])
        
        context.user_data['current_number_id'] = number_id
        
        if is_qr:
            query.edit_message_text("📷 Отправьте фото с QR кодом:")
            return WAITING_FOR_QR_PHOTO
        else:
            query.edit_message_text("📷 Отправьте фото с кодом:")
            return WAITING_FOR_CODE_PHOTO
    
    elif data.startswith('max_take_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        account_id = int(data.split('_')[2])
        
        if db.take_max_account(account_id, user_id):
            account = db.get_max_account_by_id(account_id)
            query.edit_message_text(
                f"✅ Вы взяли MAX аккаунт #{account_id}\n"
                f"📞 Номер: {account[1]}\n\n"
                f"Теперь вы можете:\n"
                f"• Запросить код (когда начнете вход)\n"
                f"• Запросить доп информацию\n"
                f"• Отметить активацию",
                reply_markup=get_max_action_keyboard(account_id, user_id, 'in_progress')
            )
        else:
            query.edit_message_text("❌ Аккаунт уже взят другим.")
    
    elif data.startswith('max_request_code_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        account_id = int(data.split('_')[3])
        
        if db.request_max_code(account_id, user_id):
            account = db.get_max_account_by_id(account_id)
            
            context.bot.send_message(
                chat_id=account[2],
                text=f"🔑 Холодка начала вход в MAX аккаунт {account[1]}!\n"
                     f"Вам придет SMS с кодом. Отправьте его сюда:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📝 Отправить код", callback_data=f"max_send_code_{account_id}")
                ]])
            )
            
            query.edit_message_text(
                f"✅ Запрос кода отправлен пользователю!\n"
                f"Ожидайте, когда пользователь пришлет код.",
                reply_markup=get_max_action_keyboard(account_id, user_id, 'waiting_code')
            )
        else:
            query.edit_message_text("❌ Ошибка при запросе кода.")
    
    elif data.startswith('max_request_extra_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        account_id = int(data.split('_')[3])
        context.user_data['current_max_extra_id'] = account_id
        
        query.edit_message_text(
            "📝 Введите дополнительную информацию, которую хотите запросить у пользователя:"
        )
        return WAITING_FOR_MAX_EXTRA_INFO
    
    elif data.startswith('max_activated_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        account_id = int(data.split('_')[2])
        account = db.get_max_account_by_id(account_id)
        
        activated_time = datetime.now()
        db.update_max_status(
            account_id,
            'activated',
            activated_at=activated_time,
            in_queue=0
        )
        
        context.bot.send_message(
            chat_id=account[2],
            text=f"✅ MAX аккаунт {account[1]} успешно активирован!\n"
                 f"⏱ Время активации: {activated_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        query.edit_message_text(
            f"✅ MAX аккаунт #{account_id} активирован.\n"
            f"⏱ Время: {activated_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    
    elif data.startswith('max_failed_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        account_id = int(data.split('_')[2])
        account = db.get_max_account_by_id(account_id)
        
        db.update_max_status(
            account_id,
            'failed',
            in_queue=0,
            taken_by=None
        )
        
        context.bot.send_message(
            chat_id=account[2],
            text=f"❌ MAX аккаунт {account[1]} не удалось активировать.\n"
                 f"Попробуйте позже."
        )
        
        query.edit_message_text(f"❌ MAX аккаунт #{account_id} отмечен как неудачный.")
    
    elif data.startswith('max_crashed_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        account_id = int(data.split('_')[2])
        account = db.get_max_account_by_id(account_id)
        
        if account and account[7]:
            crashed_time = datetime.now()
            activated_time = datetime.strptime(account[7], '%Y-%m-%d %H:%M:%S.%f')
            work_duration = int((crashed_time - activated_time).total_seconds())
            
            db.update_max_status(
                account_id,
                'crashed',
                crashed_at=crashed_time,
                total_work_time=work_duration,
                in_queue=0,
                taken_by=None
            )
            
            db.update_user_stats(account[2], 'crashed', platform='max')
            db.add_working_time(account[2], work_duration, platform='max')
            
            hours = work_duration // 3600
            minutes = (work_duration % 3600) // 60
            days = hours // 24
            hours = hours % 24
            time_str = f"{days}д {hours}ч {minutes}мин" if days > 0 else f"{hours}ч {minutes}мин"
            
            context.bot.send_message(
                chat_id=account[2],
                text=f"💥 MAX аккаунт {account[1]} слетел!\n"
                     f"⏱ Проработал: {time_str}"
            )
            
            query.edit_message_text(f"💥 MAX #{account_id} слетел. Проработал: {time_str}")
    
    elif data.startswith('max_send_code_'):
        account_id = int(data.split('_')[3])
        context.user_data['current_max_account_id'] = account_id
        
        query.edit_message_text(
            "📝 Отправьте код из SMS, который пришел на ваш номер:"
        )
        return WAITING_FOR_MAX_CODE
    
    elif data.startswith('activated_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        number_id = int(data.split('_')[1])
        number = db.get_number_by_id(number_id)
        
        if number:
            activated_time = datetime.now()
            db.update_number_status(
                number_id, 
                'activated', 
                activated_at=activated_time,
                in_queue=0
            )
            
            context.bot.send_message(
                chat_id=number[2],
                text=f"✅ Номер {number[1]} успешно активирован!\n"
                     f"⏱ Время активации: {activated_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            query.edit_message_text(
                f"✅ Номер #{number_id} активирован.\n"
                f"⏱ Время: {activated_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
    
    elif data.startswith('failed_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        number_id = int(data.split('_')[1])
        number = db.get_number_by_id(number_id)
        
        if number:
            db.update_number_status(number_id, 'failed', in_queue=0, taken_by=None)
            
            context.bot.send_message(
                chat_id=number[2],
                text=f"❌ Номер {number[1]} не удалось активировать.\n"
                     f"Попробуйте позже.",
                reply_markup=get_retry_keyboard(number_id)
            )
            
            query.edit_message_text(f"❌ Номер #{number_id} отмечен как неудачный.")
    
    elif data.startswith('crashed_'):
        if role not in ['cold', 'helper', 'owner']:
            query.edit_message_text("❌ У вас нет прав.")
            return
        
        number_id = int(data.split('_')[1])
        number = db.get_number_by_id(number_id)
        
        if number and number[7]:
            crashed_time = datetime.now()
            activated_time = datetime.strptime(number[7], '%Y-%m-%d %H:%M:%S.%f')
            work_duration = int((crashed_time - activated_time).total_seconds())
            
            db.update_number_status(
                number_id, 
                'crashed', 
                crashed_at=crashed_time,
                total_work_time=work_duration,
                in_queue=0,
                taken_by=None
            )
            
            db.update_user_stats(number[2], 'crashed', platform='whatsapp')
            db.add_working_time(number[2], work_duration, platform='whatsapp')
            
            hours = work_duration // 3600
            minutes = (work_duration % 3600) // 60
            days = hours // 24
            hours = hours % 24
            time_str = f"{days}д {hours}ч {minutes}мин" if days > 0 else f"{hours}ч {minutes}мин"
            
            context.bot.send_message(
                chat_id=number[2],
                text=f"💥 Номер {number[1]} слетел!\n"
                     f"⏱ Проработал: {time_str}"
            )
            
            query.edit_message_text(f"💥 Номер #{number_id} слетел. Проработал: {time_str}")
    
    elif data.startswith('code_entered_'):
        number_id = int(data.split('_')[2])
        number = db.get_number_by_id(number_id)
        
        if number and number[2] == user_id:
            db.update_number_status(
                number_id,
                'code_entered',
                code_entered_at=datetime.now()
            )
            
            query.edit_message_text(f"✅ Код подтвержден!")
            
            if number[13]:
                try:
                    context.bot.send_message(
                        chat_id=number[13],
                        text=f"🔔 Пользователь подтвердил ввод кода для номера {number[1]}\n"
                             f"Заявка #{number_id}\n"
                             f"Теперь можно проверить активацию.",
                        reply_markup=get_code_action_keyboard(number_id)
                    )
                except:
                    pass
    
    elif data.startswith('retry_'):
        number_id = int(data.split('_')[1])
        number = db.get_number_by_id(number_id)
        
        if number and number[2] == user_id:
            db.update_number_status(
                number_id,
                'pending',
                in_queue=1,
                taken_by=None,
                code_photo_id=None,
                qr_photo_id=None
            )
            
            cold_staff = db.get_all_cold_staff()
            for cold_id in cold_staff:
                try:
                    context.bot.send_message(
                        chat_id=cold_id,
                        text=f"🔄 Номер #{number_id} снова в очереди!\n"
                             f"📞 Номер: {number[1]}\n"
                             f"Пользователь хочет попробовать снова."
                    )
                except:
                    pass
            
            query.edit_message_text("✅ Номер возвращен в очередь.")
    
    elif data.startswith('cancel_number_'):
        number_id = int(data.split('_')[2])
        number = db.get_number_by_id(number_id)
        
        if number and number[2] == user_id:
            db.update_number_status(number_id, 'cancelled', in_queue=0, taken_by=None)
            query.edit_message_text("❌ Номер отменен.")
    
    elif data.startswith('wa_queue_keep_'):
        number_id = int(data.split('_')[3])
        db.cursor.execute('UPDATE numbers SET last_queue_notification = ? WHERE id = ?', (datetime.now(), number_id))
        db.conn.commit()
        query.edit_message_text("✅ Номер останется в очереди.")
    
    elif data.startswith('wa_queue_remove_'):
        number_id = int(data.split('_')[3])
        db.update_number_status(number_id, 'cancelled', in_queue=0, taken_by=None)
        query.edit_message_text("❌ Номер убран из очереди.")
    
    elif data.startswith('max_queue_keep_'):
        account_id = int(data.split('_')[3])
        db.cursor.execute('UPDATE max_accounts SET last_queue_notification = ? WHERE id = ?', (datetime.now(), account_id))
        db.conn.commit()
        query.edit_message_text("✅ Аккаунт останется в очереди.")
    
    elif data.startswith('max_queue_remove_'):
        account_id = int(data.split('_')[3])
        db.update_max_status(account_id, 'cancelled', in_queue=0, taken_by=None)
        query.edit_message_text("❌ Аккаунт убран из очереди.")

def handle_whatsapp_code_photo(update: Update, context: CallbackContext):
    number_id = context.user_data.get('current_number_id')
    
    if not number_id:
        update.message.reply_text("❌ Ошибка: не найден номер заявки.")
        return ConversationHandler.END
    
    number = db.get_number_by_id(number_id)
    if not number:
        update.message.reply_text("❌ Ошибка: заявка не найдена.")
        return ConversationHandler.END
    
    photo = update.message.photo[-1]
    photo_id = photo.file_id
    
    db.update_number_status(
        number_id,
        'code_sent',
        code_photo_id=photo_id,
        code_sent_at=datetime.now()
    )
    
    type_text = "Код" if number[12] == 'code' else "QR код"
    context.bot.send_photo(
        chat_id=number[2],
        photo=photo_id,
        caption=f"📷 {type_text} для WhatsApp {number[1]}\n\n"
                f"Введите код и нажмите 'Код введен'",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Код введен", callback_data=f"code_entered_{number_id}")
        ]])
    )
    
    role = db.get_user_role(update.effective_user.id)
    keyboard = get_cold_keyboard() if role == 'cold' else get_helper_keyboard()
    
    update.message.reply_text(
        f"✅ {type_text} отправлен пользователю!",
        reply_markup=keyboard
    )
    
    context.user_data.pop('current_number_id', None)
    return ConversationHandler.END

def handle_max_code_input(update: Update, context: CallbackContext):
    code = update.message.text.strip()
    account_id = context.user_data.get('current_max_account_id')
    
    if not account_id:
        update.message.reply_text("❌ Ошибка: не найден аккаунт.")
        return ConversationHandler.END
    
    cold_id = db.submit_max_code(account_id, code)
    
    if cold_id:
        account = db.get_max_account_by_id(account_id)
        context.bot.send_message(
            chat_id=cold_id,
            text=f"🔑 Получен код для MAX аккаунта #{account_id}\n"
                 f"📞 Номер: {account[1]}\n"
                 f"🔐 Код: {code}\n\n"
                 f"Теперь можно продолжить вход.",
            reply_markup=get_max_action_keyboard(account_id, cold_id, 'code_received')
        )
        
        update.message.reply_text(
            "✅ Код отправлен холодке! Ожидайте результата активации.",
            reply_markup=get_user_keyboard()
        )
    else:
        update.message.reply_text(
            "❌ Ошибка при отправке кода.",
            reply_markup=get_user_keyboard()
        )
    
    context.user_data.pop('current_max_account_id', None)
    return ConversationHandler.END

def handle_max_extra_info(update: Update, context: CallbackContext):
    extra_text = update.message.text
    account_id = context.user_data.get('current_max_extra_id')
    user_id = update.effective_user.id
    
    if not account_id:
        update.message.reply_text("❌ Ошибка: не найден аккаунт.")
        return ConversationHandler.END
    
    account = db.get_max_account_by_id(account_id)
    
    if db.request_max_extra_info(account_id, user_id, extra_text):
        context.bot.send_message(
            chat_id=account[2],
            text=f"📝 Холодка запрашивает дополнительную информацию для MAX {account[1]}:\n\n"
                 f"💬 {extra_text}\n\n"
                 f"Нажмите кнопку ниже, чтобы ответить:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📝 Ответить", callback_data=f"max_reply_extra_{account_id}")
            ]])
        )
        
        role = db.get_user_role(user_id)
        keyboard = get_cold_keyboard() if role == 'cold' else get_helper_keyboard()
        
        update.message.reply_text(
            f"✅ Запрос отправлен пользователю!",
            reply_markup=keyboard
        )
    else:
        role = db.get_user_role(user_id)
        keyboard = get_cold_keyboard() if role == 'cold' else get_helper_keyboard()
        
        update.message.reply_text(
            "❌ Ошибка при отправке запроса.",
            reply_markup=keyboard
        )
    
    context.user_data.pop('current_max_extra_id', None)
    return ConversationHandler.END

def handle_max_extra_reply(update: Update, context: CallbackContext):
    reply_text = update.message.text
    account_id = context.user_data.get('current_max_extra_account_id')
    
    if not account_id:
        update.message.reply_text("❌ Ошибка: не найден аккаунт.")
        return ConversationHandler.END
    
    result = db.submit_max_extra_reply(account_id, reply_text)
    
    if result:
        cold_id, phone = result
        context.bot.send_message(
            chat_id=cold_id,
            text=f"📝 Получен ответ на доп запрос для MAX #{account_id}\n"
                 f"📞 Номер: {phone}\n"
                 f"💬 Ответ: {reply_text}",
            reply_markup=get_max_action_keyboard(account_id, cold_id, 'code_received')
        )
        
        update.message.reply_text(
            "✅ Ответ отправлен холодке!",
            reply_markup=get_user_keyboard()
        )
    else:
        update.message.reply_text(
            "❌ Ошибка при отправке ответа.",
            reply_markup=get_user_keyboard()
        )
    
    context.user_data.pop('current_max_extra_account_id', None)
    return ConversationHandler.END

def handle_fine_user_input(update: Update, context: CallbackContext):
    try:
        target_user_id = int(update.message.text.strip())
        context.user_data['fine_target'] = target_user_id
        
        update.message.reply_text("Введите сумму штрафа в $:")
        return WAITING_FOR_FINE_AMOUNT
    except:
        update.message.reply_text("❌ Неверный ID. Попробуйте снова.")
        return ConversationHandler.END

def handle_fine_amount_input(update: Update, context: CallbackContext):
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
        
        context.user_data['fine_amount'] = amount
        
        update.message.reply_text("Введите причину штрафа:")
        return WAITING_FOR_FINE_REASON
    except:
        update.message.reply_text("❌ Неверная сумма. Введите число больше 0.")
        return ConversationHandler.END

def handle_fine_reason_input(update: Update, context: CallbackContext):
    reason = update.message.text
    target_id = context.user_data.get('fine_target')
    amount = context.user_data.get('fine_amount')
    issuer_id = update.effective_user.id
    
    fine_id = db.add_fine(target_id, issuer_id, amount, reason)
    
    try:
        context.bot.send_message(
            chat_id=target_id,
            text=f"⚠️ **Вам наложен штраф!**\n\n"
                 f"💰 Сумма: ${amount}\n"
                 f"📝 Причина: {reason}\n"
                 f"👮 Выдал: @{update.effective_user.username}\n\n"
                 f"Для оплаты обратитесь к @popopep",
            parse_mode='Markdown'
        )
    except:
        pass
    
    update.message.reply_text(
        f"✅ Штраф #{fine_id} наложен!\n"
        f"👤 Пользователь: {target_id}\n"
        f"💰 Сумма: ${amount}\n"
        f"📝 Причина: {reason}"
    )
    
    context.user_data.pop('fine_target', None)
    context.user_data.pop('fine_amount', None)
    
    return ConversationHandler.END

def handle_fine_reset_input(update: Update, context: CallbackContext):
    try:
        fine_id = int(update.message.text.strip())
        reset_by = update.effective_user.id
        
        if db.reset_fine(fine_id, reset_by):
            update.message.reply_text(f"✅ Штраф #{fine_id} обнулен!")
        else:
            update.message.reply_text("❌ Штраф не найден или уже оплачен.")
    except:
        update.message.reply_text("❌ Неверный ID штрафа.")
    
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    role = db.get_user_role(update.effective_user.id)
    
    if role == 'owner':
        keyboard = get_owner_keyboard()
    elif role == 'helper':
        keyboard = get_helper_keyboard()
    elif role == 'cold':
        keyboard = get_cold_keyboard()
    else:
        keyboard = get_user_keyboard()
    
    update.message.reply_text(
        "Действие отменено.",
        reply_markup=keyboard
    )
    return ConversationHandler.END

def queue_check_job(context: CallbackContext):
    db.cursor.execute('''
        SELECT id, user_id, queue_position, phone_number
        FROM numbers 
        WHERE status = 'pending' 
        AND in_queue = 1
        AND (last_queue_notification IS NULL OR last_queue_notification < datetime('now', '-5 minutes'))
        ORDER BY queue_position
        LIMIT 10
    ''')
    
    numbers_to_check = db.cursor.fetchall()
    
    for number_id, user_id, position, phone in numbers_to_check:
        try:
            context.bot.send_message(
                chat_id=user_id,
                text=f"⏳ Ваш WhatsApp номер {phone} все еще в очереди (позиция: {position}).\n"
                     f"Хотите оставить его?",
                reply_markup=get_queue_check_keyboard(number_id, 'whatsapp')
            )
            db.cursor.execute('UPDATE numbers SET last_queue_notification = ? WHERE id = ?', (datetime.now(), number_id))
            db.conn.commit()
        except Exception as e:
            logger.error(f"Failed to send queue check: {e}")
    
    db.cursor.execute('''
        SELECT id, user_id, queue_position, phone_number
        FROM max_accounts 
        WHERE status = 'pending' 
        AND in_queue = 1
        AND (last_queue_notification IS NULL OR last_queue_notification < datetime('now', '-5 minutes'))
        ORDER BY queue_position
        LIMIT 10
    ''')
    
    max_to_check = db.cursor.fetchall()
    
    for acc_id, user_id, position, phone in max_to_check:
        try:
            context.bot.send_message(
                chat_id=user_id,
                text=f"⏳ Ваш MAX аккаунт {phone} все еще в очереди (позиция: {position}).\n"
                     f"Хотите оставить его?",
                reply_markup=get_queue_check_keyboard(acc_id, 'max')
            )
            db.cursor.execute('UPDATE max_accounts SET last_queue_notification = ? WHERE id = ?', (datetime.now(), acc_id))
            db.conn.commit()
        except Exception as e:
            logger.error(f"Failed to send MAX queue check: {e}")

def check_active_numbers(context: CallbackContext):
    active_numbers = db.get_active_numbers()
    
    for number in active_numbers:
        if number[7]:
            activated = datetime.strptime(number[7], '%Y-%m-%d %H:%M:%S.%f')
            now = datetime.now()
            work_duration = int((now - activated).total_seconds())
            
            if work_duration % 600 == 0:
                db.add_working_time(number[2], 600, platform='whatsapp')
    
    active_max = db.get_active_max_accounts()
    
    for acc in active_max:
        if acc[7]:
            activated = datetime.strptime(acc[7], '%Y-%m-%d %H:%M:%S.%f')
            now = datetime.now()
            work_duration = int((now - activated).total_seconds())
            
            if work_duration % 600 == 0:
                db.add_working_time(acc[2], 600, platform='max')

def main():
    updater = Updater(token=config.BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # ConversationHandler для соглашения
    dp.add_handler(CallbackQueryHandler(handle_agreement, pattern='^accept_agreement$'))
    
    # WhatsApp номер
    wa_number_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.text("📱 WhatsApp"), handle_message)],
        states={
            WAITING_FOR_NUMBER: [MessageHandler(Filters.text & ~Filters.command, handle_whatsapp_number_input)],
            WAITING_FOR_TYPE: [CallbackQueryHandler(handle_type_selection, pattern='^type_')]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(wa_number_conv)
    
    # MAX номер
    max_number_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.text("📲 MAX"), handle_message)],
        states={
            WAITING_FOR_MAX_NUMBER: [MessageHandler(Filters.text & ~Filters.command, handle_max_number_input)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(max_number_conv)
    
    # Фото для WhatsApp
    wa_photo_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_callback, pattern='^wa_send_code_'),
            CallbackQueryHandler(handle_callback, pattern='^wa_send_qr_'),
            CallbackQueryHandler(handle_callback, pattern='^wa_take_code_'),
            CallbackQueryHandler(handle_callback, pattern='^wa_take_qr_')
        ],
        states={
            WAITING_FOR_CODE_PHOTO: [MessageHandler(Filters.photo, handle_whatsapp_code_photo)],
            WAITING_FOR_QR_PHOTO: [MessageHandler(Filters.photo, handle_whatsapp_code_photo)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(wa_photo_conv)
    
    # Код для MAX
    max_code_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^max_send_code_')],
        states={
            WAITING_FOR_MAX_CODE: [MessageHandler(Filters.text & ~Filters.command, handle_max_code_input)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(max_code_conv)
    
    # Доп информация для MAX
    max_extra_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^max_request_extra_')],
        states={
            WAITING_FOR_MAX_EXTRA_INFO: [MessageHandler(Filters.text & ~Filters.command, handle_max_extra_info)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(max_extra_conv)
    
    # Ответ на доп запрос
    max_user_reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^max_reply_extra_')],
        states={
            WAITING_FOR_MAX_USER_REPLY: [MessageHandler(Filters.text & ~Filters.command, handle_max_extra_reply)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(max_user_reply_conv)
    
    # Штрафы
    fines_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^fines_')],
        states={
            WAITING_FOR_FINE_USER: [MessageHandler(Filters.text & ~Filters.command, handle_fine_user_input)],
            WAITING_FOR_FINE_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, handle_fine_amount_input)],
            WAITING_FOR_FINE_REASON: [MessageHandler(Filters.text & ~Filters.command, handle_fine_reason_input)],
            WAITING_FOR_FINE_RESET: [MessageHandler(Filters.text & ~Filters.command, handle_fine_reset_input)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(fines_conv)
    
    # Изменение ролей
    role_change_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.text("👥 Управление ролями"), handle_message)],
        states={
            WAITING_FOR_ROLE_CHANGE: [MessageHandler(Filters.text & ~Filters.command, handle_role_change)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(role_change_conv)
    
    # Удаление из очереди
    queue_remove_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.text("🗑 Удалить из очереди"), handle_message)],
        states={
            WAITING_FOR_QUEUE_REMOVE: [MessageHandler(Filters.text & ~Filters.command, handle_queue_remove)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dp.add_handler(queue_remove_conv)
    
    # Основные обработчики
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CallbackQueryHandler(handle_callback))
    
    # Фоновые задачи
    from telegram.ext import JobQueue
    job_queue = updater.job_queue
    job_queue.run_repeating(check_active_numbers, interval=600, first=10)
    job_queue.run_repeating(queue_check_job, interval=300, first=60)
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()