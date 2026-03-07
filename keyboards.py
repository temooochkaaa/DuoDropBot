from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def back(target="menu"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Назад", callback_data=target)]
    ])

def main_menu(role):
    buttons = [
        [InlineKeyboardButton("📱 Сдать номер", callback_data="submit_menu")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("🔄 Проверить очередь", callback_data="check_queue")],
        [InlineKeyboardButton("🔰 Поддержка", callback_data="support")]
    ]

    if role in ["cold", "helper", "owner"]:
        buttons.append([InlineKeyboardButton("❄️ Панель холодки", callback_data="cold_panel")])

    if role in ["helper", "owner"]:
        buttons.append([InlineKeyboardButton("👥 Панель помощника", callback_data="helper_panel")])

    if role == "owner":
        buttons.append([InlineKeyboardButton("👑 Панель владельца", callback_data="owner_panel")])

    return InlineKeyboardMarkup(buttons)

def submit_menu():
    buttons = [
        [InlineKeyboardButton("📱 WhatsApp", callback_data="submit_whatsapp"),
         InlineKeyboardButton("📲 MAX", callback_data="submit_max")],
        [InlineKeyboardButton("⬅ Назад", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(buttons)

def cold_panel_menu():
    buttons = [
        [InlineKeyboardButton("📨 Запросить WhatsApp", callback_data="req_whatsapp"),
         InlineKeyboardButton("📨 Запросить MAX", callback_data="req_max")],
        [InlineKeyboardButton("📋 Свободные номера", callback_data="free_numbers")],
        [InlineKeyboardButton("📋 Мои номера", callback_data="my_numbers")],
        [InlineKeyboardButton("⬅ Назад", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(buttons)

def number_actions_menu(number_id, platform, taken=False):
    buttons = []
    
    if not taken:
        if platform == "whatsapp":
            buttons = [
                [InlineKeyboardButton("📝 Взять (код)", callback_data=f"take_code_{number_id}"),
                 InlineKeyboardButton("📷 Взять (QR)", callback_data=f"take_qr_{number_id}")],
                [InlineKeyboardButton("⬅ Назад", callback_data="free_numbers")]
            ]
        else:
            buttons = [
                [InlineKeyboardButton("📲 Взять", callback_data=f"take_max_{number_id}")],
                [InlineKeyboardButton("⬅ Назад", callback_data="free_numbers")]
            ]
    else:
        if platform == "max":
            buttons = [
                [InlineKeyboardButton("🔑 Запросить код", callback_data=f"req_code_{number_id}"),
                 InlineKeyboardButton("📝 Запросить инфо", callback_data=f"req_extra_{number_id}")]
            ]
    
    return InlineKeyboardMarkup(buttons)

def status_buttons(number_id, platform):
    buttons = [
        [InlineKeyboardButton("✅ Встал", callback_data=f"activated_{number_id}"),
         InlineKeyboardButton("❌ Не встал", callback_data=f"failed_{number_id}")],
        [InlineKeyboardButton("💥 Слетел", callback_data=f"crashed_{number_id}")]
    ]
    return InlineKeyboardMarkup(buttons)

def helper_panel_menu():
    buttons = [
        [InlineKeyboardButton("📊 Статистика WhatsApp", callback_data="stats_whatsapp"),
         InlineKeyboardButton("📊 Статистика MAX", callback_data="stats_max")],
        [InlineKeyboardButton("📋 Все номера", callback_data="all_numbers")],
        [InlineKeyboardButton("🗑 Удалить номер", callback_data="remove_number")],
        [InlineKeyboardButton("⬅ Назад", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(buttons)

def owner_panel_menu():
    buttons = [
        [InlineKeyboardButton("📊 Статистика бота", callback_data="owner_stats")],
        [InlineKeyboardButton("👥 Управление ролями", callback_data="manage_roles")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")],
        [InlineKeyboardButton("⬅ Назад", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(buttons)