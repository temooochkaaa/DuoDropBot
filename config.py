import os

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
MIN_PHONE_LENGTH = 10
MAX_PHONE_LENGTH = 15
NUMBERS_PER_PAGE = 10
ALL_NUMBERS_PER_PAGE = 20
QUEUE_CHECK_INTERVAL = 300  # 5 минут
MAX_RETRY_COUNT = 3
BROADCAST_DELAY = 0.33  # Задержка между сообщениями при рассылке
CLEANUP_INTERVAL = 86400  # 24 часа - очистка старых записей
CLEANUP_DAYS = 7  # Хранить cancelled 7 дней

# Настройки БД
DB_POOL_MIN = 1
DB_POOL_MAX = 50  # Увеличено для 50+ холодников
DB_POOL_TIMEOUT = 30