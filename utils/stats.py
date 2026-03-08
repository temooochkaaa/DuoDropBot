import time
from datetime import datetime
from database import get_cursor
from config import TIMEZONE

def generate_user_stats(user_id):
    with get_cursor() as cur:
        cur.execute("""
        SELECT phone, platform, status, created_at, activated_at, crashed_at, total_work_time
        FROM numbers 
        WHERE user_id=%s
        ORDER BY created_at DESC
        """, (user_id,))
        
        rows = cur.fetchall()
    
    if not rows:
        return "📭 У вас пока нет номеров."
    
    text = f"📊 **СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ**\n\n"
    text += "=" * 40 + "\n\n"
    
    for r in rows:
        phone, platform, status, created, activated, crashed, work = r
        
        text += f"📞 **{phone}** ({platform.upper()})\n"
        text += f"   Статус: **{status}**\n"
        
        if created:
            dt = datetime.fromtimestamp(created, TIMEZONE)
            text += f"   📅 Создан: {dt.strftime('%d.%m.%Y %H:%M')}\n"
        
        if activated:
            dt = datetime.fromtimestamp(activated, TIMEZONE)
            text += f"   ✅ Активирован: {dt.strftime('%d.%m.%Y %H:%M')}\n"
        
        if crashed:
            dt = datetime.fromtimestamp(crashed, TIMEZONE)
            text += f"   💥 Слетел: {dt.strftime('%d.%m.%Y %H:%M')}\n"
        
        if work:
            hours = work // 3600
            minutes = (work % 3600) // 60
            text += f"   ⏱ Проработал: {hours}ч {minutes}мин\n"
        
        text += "-" * 30 + "\n"
    
    return text

def generate_daily_stats(platform='whatsapp'):
    today_start = int(time.time()) - 86400
    
    with get_cursor() as cur:
        cur.execute("""
        SELECT u.id, u.username, u.first_name,
               n.phone, n.status, n.created_at, n.activated_at
        FROM users u
        LEFT JOIN numbers n ON u.id = n.user_id AND n.platform=%s AND n.created_at > %s
        WHERE u.role IN ('user', 'cold')
        ORDER BY u.id, n.created_at
        """, (platform, today_start))
        
        rows = cur.fetchall()
    
    if not rows or not any(r[3] for r in rows):
        return f"📊 За сегодня нет данных по {platform.upper()}."
    
    text = f"📊 **СТАТИСТИКА {platform.upper()} ЗА СЕГОДНЯ**\n\n"
    
    current_user = None
    has_data = False
    
    for r in rows:
        uid, username, name, phone, status, created, activated = r
        
        if uid and (current_user != uid):
            current_user = uid
            display = f"@{username}" if username else name
            text += f"\n👤 **{display}** (ID: {uid})\n"
        
        if phone:
            has_data = True
            time_str = datetime.fromtimestamp(created, TIMEZONE).strftime('%H:%M')
            status_icon = "✅" if status == 'activated' else "⏳"
            text += f"   {status_icon} {phone} - {time_str}\n"
    
    return text if has_data else f"📊 За сегодня нет данных по {platform.upper()}."