from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import ADMIN_ID, MANAGER_IDS


def get_main_keyboard(user_id=None):
    buttons = [
        [KeyboardButton(text="📝 Записать работу"),
         KeyboardButton(text="📁 Мои записи")],
        [KeyboardButton(text="💰 За сегодня"),
         KeyboardButton(text="📊 За месяц")],
        [KeyboardButton(text="💳 Мой баланс"),
         KeyboardButton(text="💬 Написать вопрос")]
    ]
    if user_id and user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🖥 Админ-панель")])
    elif user_id and user_id in MANAGER_IDS:
        buttons.append([KeyboardButton(text="💼 Кабинет Эльмурзы")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_admin_keyboard():
    buttons = [
        [KeyboardButton(text="📁 Сводка день"),
         KeyboardButton(text="💸 Выдать зарплату")],
        [KeyboardButton(text="➕ Добавить"),
         KeyboardButton(text="✏️ Редактировать")],
        [KeyboardButton(text="🗑 Удалить"),
         KeyboardButton(text="🔧 Записи работников")],
        [KeyboardButton(text="💰 Деньги"),
         KeyboardButton(text="💾 Бэкап БД")],
        [KeyboardButton(text="⏰ Напоминания"),
         KeyboardButton(text="📂 Справочники")],
        [KeyboardButton(text="📢 Рассылка")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_manager_keyboard():
    buttons = [
        [KeyboardButton(text="📁 Сводка день")],
        [KeyboardButton(text="👤 Отчёт по сотрудникам"),
         KeyboardButton(text="🏭 Отчёт по цеху")],
        [KeyboardButton(text="💰 Деньги")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_add_keyboard():
    buttons = [
        [KeyboardButton(text="➕ Категория")],
        [KeyboardButton(text="➕ Вид работы")],
        [KeyboardButton(text="👤 Добавить работника")],
        [KeyboardButton(text="👻 Без Telegram (дед)")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_edit_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✏️ Редактировать категорию"),
         KeyboardButton(text="✏️ Редактировать работу")],
        [KeyboardButton(text="✏️ Расценка"),
         KeyboardButton(text="✏️ Переименовать")],
        [KeyboardButton(text="🔗 Назначить кат."),
         KeyboardButton(text="🔓 Убрать кат.")],
        [KeyboardButton(text="🔙 В админ-панель")]
    ], resize_keyboard=True)


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
        [KeyboardButton(text="📊 Сводка работников")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
