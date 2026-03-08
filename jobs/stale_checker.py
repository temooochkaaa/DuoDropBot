from database import check_stale_numbers

def check_stale_job(context):
    """Проверка зависших номеров каждые 5 минут"""
    check_stale_numbers()