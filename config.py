import os
import pytz

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set in environment variables")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not set in environment variables")

# ID группы для запросов холодки
GROUP_ID = int(os.getenv("GROUP_ID", "-1002962459513"))

# ID владельца
OWNER_ID = int(os.getenv("OWNER_ID", "7787440009"))

# Поддержка
SUPPORT = os.getenv("SUPPORT", "@popopep")

# Ссылки
GROUP_LINK = os.getenv("GROUP_LINK", "https://t.me/duodrop")
REPUTATION_LINK = os.getenv("REPUTATION_LINK", "https://t.me/reputatiooonnn")
ADAPTER_LINK = os.getenv("ADAPTER_LINK", "https://t.me/DuoDrop")

# Лимиты и настройки пагинации
MAX_ACTIVE_NUMBERS = 30
MAX_ACTIVE_COLD = 5
MIN_PHONE_LENGTH = 10
MAX_PHONE_LENGTH = 15
NUMBERS_PER_PAGE = 10
ALL_NUMBERS_PER_PAGE = 20
QUEUE_CHECK_INTERVAL = 300  # 5 минут
MAX_RETRY_COUNT = 3
BROADCAST_DELAY = 0.33
CLEANUP_INTERVAL = 86400  # 24 часа
CLEANUP_DAYS = 30  # Хранить 30 дней
EXTRA_REQUEST_COOLDOWN = 300  # 5 минут
REQUEST_NUMBER_COOLDOWN = 30  # 30 секунд между запросами в группу
BUTTON_COOLDOWN = 2  # 2 секунды между нажатиями кнопок

# Настройки БД
DB_POOL_MIN = 1
DB_POOL_MAX = 50
DB_POOL_TIMEOUT = 30
DB_RETRY_COUNT = 3
DB_RETRY_DELAY = 1

# Часовой пояс
TIMEZONE = pytz.timezone("Europe/Moscow")