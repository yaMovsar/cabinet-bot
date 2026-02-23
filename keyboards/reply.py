from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import ADMIN_ID, MANAGER_IDS


def get_main_keyboard(user_id=None):
    buttons = [
        [KeyboardButton(text="📝 Записать работу"),
         KeyboardButton(text="📋 Мои записи")],
        [KeyboardButton(text="💰 За сегодня"),
         KeyboardButton(text="📊 За месяц")],
        [KeyboardButton(text="💳 Мой баланс")],
        [KeyboardButton(text="💬 Поддержка")],  # Добавлена кнопка
    ]
    if user_id and user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="👑 Админ-панель")])
    elif user_id and user_id in MANAGER_IDS:
        buttons.append([KeyboardButton(text="💼 Кабинет Эльмурзы")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_admin_keyboard():
    buttons = [
        [KeyboardButton(text="📋 Сводка день"),
         KeyboardButton(text="📋 Сводка месяц")],
        [KeyboardButton(text="📥 Отчёт месяц"),
         KeyboardButton(text="📥 Отчёт работник")],
        [KeyboardButton(text="➕ Добавить"),
         KeyboardButton(text="✏️ Редактировать")],
        [KeyboardButton(text="🗑 Удалить"),
         KeyboardButton(text="📂 Справочники")],
        [KeyboardButton(text="💰 Деньги"),
         KeyboardButton(text="💾 Бэкап БД")],
        [KeyboardButton(text="⏰ Напоминания")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_manager_keyboard():
    buttons = [
        [KeyboardButton(text="📋 Сводка день"),
         KeyboardButton(text="📋 Сводка месяц")],
        [KeyboardButton(text="📥 Отчёт месяц"),
         KeyboardButton(text="📥 Отчёт работник")],
        [KeyboardButton(text="📂 Справочники")],
        [KeyboardButton(text="💰 Деньги")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_add_keyboard():
    buttons = [
        [KeyboardButton(text="➕ Категория")],
        [KeyboardButton(text="➕ Вид работы")],
        [KeyboardButton(text="👤 Добавить работника")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_edit_keyboard():
    buttons = [
        [KeyboardButton(text="🔗 Назначить кат."),
         KeyboardButton(text="🔓 Убрать кат.")],
        [KeyboardButton(text="✏️ Расценка"),
         KeyboardButton(text="✏️ Переименовать")],
        [KeyboardButton(text="📂 Ред. категорию"),
         KeyboardButton(text="📝 Ред. работу")],  # Добавлены кнопки
        [KeyboardButton(text="🔧 Записи работников")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_delete_keyboard():
    buttons = [
        [KeyboardButton(text="🗑 Уд. категорию")],
        [KeyboardButton(text="🗑 Уд. работу")],
        [KeyboardButton(text="🗑 Уд. работника")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_info_keyboard():
    buttons = [
        [KeyboardButton(text="📂 Категории")],
        [KeyboardButton(text="📄 Прайс-лист")],
        [KeyboardButton(text="👥 Работники")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_money_keyboard():
    buttons = [
        [KeyboardButton(text="💳 Выдать аванс"),
         KeyboardButton(text="💳 Удалить аванс")],
        [KeyboardButton(text="⚠️ Выписать штраф"),
         KeyboardButton(text="⚠️ Удалить штраф")],
        [KeyboardButton(text="💰 Баланс работников")],
        [KeyboardButton(text="📊 Заработок за месяц")],
        [KeyboardButton(text="🏆 Рейтинг работников")],
        [KeyboardButton(text="💼 Итоги месяца")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)