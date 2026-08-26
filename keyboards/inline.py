from datetime import date, timedelta
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def make_date_picker(callback_prefix: str, cancel_callback: str = "cancel"):
    today = date.today()
    yesterday = today - timedelta(days=1)
    rows = [[InlineKeyboardButton(
        text=f"📅 Сегодня ({today.strftime('%d.%m')})",
        callback_data=f"{callback_prefix}:{today.isoformat()}"
    )]]
    # прошлый месяц закрыт — «вчера» показываем только внутри текущего месяца
    if yesterday.month == today.month:
        rows.append([InlineKeyboardButton(
            text=f"📅 Вчера ({yesterday.strftime('%d.%m')})",
            callback_data=f"{callback_prefix}:{yesterday.isoformat()}"
        )])
        rows.append([InlineKeyboardButton(
            text="📅 Выбрать дату...",
            callback_data=f"{callback_prefix}:custom"
        )])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_work_buttons(cat_items, columns=2):
    buttons = []
    row = []
    for code, name, price, cat, price_type in cat_items:
        if price_type == 'custom':
            # подработка (шабашка) — сумму вводит работник, всегда отдельной строкой
            if row:
                buttons.append(row)
                row = []
            buttons.append([InlineKeyboardButton(
                text=f"💵 {name}",
                callback_data=f"work:{code}"
            )])
            continue
        row.append(InlineKeyboardButton(
            text=f"{name} {int(price)}₽",
            callback_data=f"work:{code}"
        ))
        if len(row) == columns:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


def make_confirm_buttons(yes_callback: str, no_callback: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да!", callback_data=yes_callback)],
        [InlineKeyboardButton(text="❌ Нет", callback_data=no_callback)]
    ])


def make_cancel_button(callback: str = "cancel"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=callback)]
    ])


def make_back_button(callback: str, text: str = "🔙 Назад"):
    return [InlineKeyboardButton(text=text, callback_data=callback)]