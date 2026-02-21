import asyncio
import logging
import os
from datetime import date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID, MANAGER_ID

from database import (
    init_db, add_work, get_daily_total, get_monthly_total,
    get_workers_without_records, get_all_workers_daily_summary,
    get_all_workers_monthly_summary,
    get_price_list, get_price_list_for_worker,
    add_worker, delete_last_entry, add_price_item,
    update_price, get_all_workers,
    add_category, get_categories,
    assign_category_to_worker, remove_category_from_worker,
    get_worker_categories, get_workers_in_category,
    delete_category, delete_price_item_permanently, delete_worker,
    get_monthly_by_days,
    get_today_entries, get_worker_recent_entries,
    delete_entry_by_id, update_entry_quantity, get_entry_by_id,
    get_worker_monthly_details, get_all_workers_monthly_details,
    get_admin_monthly_detailed_all,
    add_advance, get_worker_advances, get_worker_advances_total,
    delete_advance, get_all_advances_monthly,
    get_worker_entries_by_custom_date
)

from reports import generate_monthly_report, generate_worker_report

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()


# ==================== РОЛИ ====================

def is_admin(uid):
    return uid == ADMIN_ID

def is_manager(uid):
    return uid == MANAGER_ID

def is_staff(uid):
    return uid == ADMIN_ID or uid == MANAGER_ID


# ==================== СОСТОЯНИЯ ====================

class WorkEntry(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()
    choosing_category = State()
    choosing_work = State()
    entering_quantity = State()
    confirming_large = State()    # НОВОЕ

class AdminAddCategory(StatesGroup):
    entering_code = State()
    entering_name = State()
    entering_emoji = State()

class AdminAddWork(StatesGroup):
    choosing_category = State()
    entering_code = State()
    entering_name = State()
    entering_price = State()

class AdminAddWorker(StatesGroup):
    entering_id = State()
    entering_name = State()

class AdminAssignCategory(StatesGroup):
    choosing_worker = State()
    choosing_category = State()

class AdminRemoveCategory(StatesGroup):
    choosing_worker = State()
    choosing_category = State()

class AdminEditPrice(StatesGroup):
    choosing_item = State()
    entering_new_price = State()

class AdminDeleteCategory(StatesGroup):
    choosing = State()
    confirming = State()

class AdminDeleteWork(StatesGroup):
    choosing = State()
    confirming = State()

class AdminDeleteWorker(StatesGroup):
    choosing = State()
    confirming = State()

class ReportWorker(StatesGroup):
    choosing_worker = State()

class WorkerDeleteEntry(StatesGroup):
    choosing_entry = State()
    confirming = State()

class AdminManageEntries(StatesGroup):
    choosing_worker = State()
    viewing_entries = State()
    choosing_action = State()
    entering_new_quantity = State()
    confirming_delete = State()

class AdminAdvance(StatesGroup):
    choosing_worker = State()
    entering_amount = State()
    entering_comment = State()

class AdminDeleteAdvance(StatesGroup):
    choosing_worker = State()
    choosing_advance = State()
    confirming = State()

class ViewEntries(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()

# ==================== КЛАВИАТУРЫ ====================

def get_main_keyboard(user_id=None):
    buttons = [
        [KeyboardButton(text="📝 Записать работу"),
         KeyboardButton(text="📋 Мои записи")],
        [KeyboardButton(text="💰 За сегодня"),
         KeyboardButton(text="📊 За месяц")],
    ]
    if user_id and is_admin(user_id):
        buttons.append([KeyboardButton(text="👑 Админ-панель")])
    elif user_id and is_manager(user_id):
        buttons.append([KeyboardButton(text="📊 Панель отчётов")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_admin_keyboard():
    """Главная админ-панель"""
    buttons = [
        [KeyboardButton(text="📋 Сводка день"),
         KeyboardButton(text="📋 Сводка месяц")],
        [KeyboardButton(text="📥 Отчёт месяц"),
         KeyboardButton(text="📥 Отчёт работник")],
        [KeyboardButton(text="➕ Добавить"),
         KeyboardButton(text="✏️ Редактировать")],
        [KeyboardButton(text="🗑 Удалить"),
         KeyboardButton(text="📂 Справочники")],
        [KeyboardButton(text="💾 Бэкап БД")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_add_keyboard():
    """Подменю: Добавить"""
    buttons = [
        [KeyboardButton(text="➕ Категория")],
        [KeyboardButton(text="➕ Вид работы")],
        [KeyboardButton(text="👤 Добавить работника")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


@dp.message(WorkEntry.entering_quantity)
async def quantity_entered(message: types.Message, state: FSMContext):
    try:
        qty = int(message.text)
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число!")
        return

    data = await state.get_data()
    info = data["work_info"]
    total = qty * info["price"]

    # Подтверждение если сумма > 10000
    if total > 10000:
        await state.update_data(quantity=qty)
        buttons = [
            [InlineKeyboardButton(text="✅ Да, записать!", callback_data="confirm_large:yes")],
            [InlineKeyboardButton(text="✏️ Изменить количество", callback_data="confirm_large:edit")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_large:cancel")]
        ]
        work_date = data.get("work_date", date.today().isoformat())
        d = work_date.split("-")
        date_str = f"{d[2]}.{d[1]}.{d[0]}"
        await message.answer(
            f"⚠️ **Внимание! Большая сумма!**\n\n"
            f"📅 Дата: **{date_str}**\n"
            f"📦 {info['name']} × {qty} = **{int(total)} ₽**\n\n"
            f"Всё верно?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.confirming_large)
        return

    # Обычная запись
    await save_work_entry(message, state, qty)


@dp.callback_query(F.data.startswith("confirm_large:"), WorkEntry.confirming_large)
async def confirm_large_entry(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]

    if action == "yes":
        data = await state.get_data()
        qty = data["quantity"]
        await callback.message.delete()
        await save_work_entry(callback.message, state, qty, user=callback.from_user)

    elif action == "edit":
        await callback.message.edit_text(
            "Введите **правильное** количество:",
            parse_mode="Markdown"
        )
        await state.set_state(WorkEntry.entering_quantity)

    elif action == "cancel":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()

    await callback.answer()


async def save_work_entry(message, state, qty, user=None):
    """Сохраняет запись о работе"""
    if user is None:
        user = message.from_user

    data = await state.get_data()
    info = data["work_info"]
    work_date = data.get("work_date", date.today().isoformat())

    total = add_work(user.id, info["code"], qty, info["price"], work_date)
    daily = get_daily_total(user.id, work_date)
    day_total = sum(r[3] for r in daily)

    d = work_date.split("-")
    date_str = f"{d[2]}.{d[1]}.{d[0]}"

    await message.answer(
        f"✅ **Записано!**\n\n"
        f"📅 Дата: **{date_str}**\n"
        f"📦 {info['name']} × {qty} = **{int(total)} ₽**\n"
        f"💰 За этот день: **{int(day_total)} ₽**",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user.id)
    )

    # Уведомление админу
    if user.id != ADMIN_ID:
        notify_text = (
            f"📬 **Новая запись!**\n\n"
            f"👤 {user.full_name}\n"
            f"📅 {date_str}\n"
            f"📦 {info['name']} × {qty} = **{int(total)} ₽**\n"
            f"💰 За этот день: **{int(day_total)} ₽**"
        )
        try:
            await bot.send_message(ADMIN_ID, notify_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Notify admin: {e}")

    if MANAGER_ID and user.id != MANAGER_ID:
        try:
            await bot.send_message(MANAGER_ID, notify_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Notify manager: {e}")

    await state.clear()

def get_delete_keyboard():
    """Подменю: Удалить"""
    buttons = [
        [KeyboardButton(text="🗑 Уд. категорию")],
        [KeyboardButton(text="🗑 Уд. работу")],
        [KeyboardButton(text="🗑 Уд. работника")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_info_keyboard():
    """Подменю: Справочники"""
    buttons = [
        [KeyboardButton(text="📂 Категории")],
        [KeyboardButton(text="📄 Прайс-лист")],
        [KeyboardButton(text="👥 Работники")],
        [KeyboardButton(text="🔙 В админ-панель")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_manager_keyboard():
    """Клавиатура менеджера — только просмотр"""
    buttons = [
        [KeyboardButton(text="📋 Сводка день"),
         KeyboardButton(text="📋 Сводка месяц")],
        [KeyboardButton(text="📥 Отчёт месяц"),
         KeyboardButton(text="📥 Отчёт работник")],
        [KeyboardButton(text="📂 Справочники")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


# ==================== УТИЛИТЫ ====================

async def send_long_message(target, text, parse_mode="Markdown"):
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        await target.answer(text, parse_mode=parse_mode)
        return
    parts = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN:
            parts.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        parts.append(current)
    for part in parts:
        if part.strip():
            await target.answer(part, parse_mode=parse_mode)


# ==================== /start ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    add_worker(uid, message.from_user.full_name)
    if is_admin(uid):
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n"
            "Вы — администратор.\n\n"
            "📌 Настройка:\n"
            "1. ➕ Добавить → Категория\n"
            "2. ➕ Добавить → Вид работы\n"
            "3. ➕ Добавить → Работника\n"
            "4. ✏️ Редактировать → Назначить кат."
        )
    elif is_manager(uid):
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n"
            "Вы — менеджер. Доступен просмотр отчётов."
        )
    else:
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n"
            "Записывайте работу каждый день!"
        )
    await message.answer(text, reply_markup=get_main_keyboard(uid))


# ==================== ЗАПИСАТЬ РАБОТУ ====================

@dp.message(F.text == "📝 Записать работу")
async def start_work_entry(message: types.Message, state: FSMContext):
    items = get_price_list_for_worker(message.from_user.id)
    if not items:
        await message.answer("⚠️ Вам не назначены категории.")
        return

    from datetime import timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)

    buttons = [
        [InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data=f"wdate:{today.isoformat()}"
        )],
        [InlineKeyboardButton(
            text=f"📅 Вчера ({yesterday.strftime('%d.%m')})",
            callback_data=f"wdate:{yesterday.isoformat()}"
        )],
        [InlineKeyboardButton(
            text="📅 Выбрать дату...",
            callback_data="wdate:custom"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ]
    await message.answer(
        "📅 За какой день записать работу?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(WorkEntry.choosing_date)


@dp.callback_query(F.data.startswith("wdate:"), WorkEntry.choosing_date)
async def work_date_chosen(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]

    if value == "custom":
        await callback.message.edit_text(
            "📅 Введите дату в формате **ДД.ММ.ГГГГ**\n\n"
            "Например: `25.05.2025`",
            parse_mode="Markdown"
        )
        await state.set_state(WorkEntry.entering_custom_date)
        await callback.answer()
        return

    chosen_date = value
    await state.update_data(work_date=chosen_date)
    await show_category_or_work(callback, state, chosen_date)
    await callback.answer()


@dp.message(WorkEntry.entering_custom_date)
async def custom_date_entered(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        parts = text.split(".")
        if len(parts) != 3:
            raise ValueError
        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])
        chosen = date(year, month, day)

        if chosen > date.today():
            await message.answer("❌ Нельзя записать на будущую дату!")
            return

        from datetime import timedelta
        if chosen < date.today() - timedelta(days=90):
            await message.answer("❌ Нельзя записать дату старше 90 дней!")
            return

    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат!\n\n"
            "Введите дату как **ДД.ММ.ГГГГ**\n"
            "Например: `25.05.2025`",
            parse_mode="Markdown"
        )
        return

    chosen_date = chosen.isoformat()
    await state.update_data(work_date=chosen_date)

    items = get_price_list_for_worker(message.from_user.id)
    worker_cats = get_worker_categories(message.from_user.id)
    d = chosen_date.split("-")
    date_str = f"{d[2]}.{d[1]}.{d[0]}"

    if len(worker_cats) == 1:
        cat_code = worker_cats[0][0]
        cat_items = [i for i in items if i[3] == cat_code]
        buttons = []
        for code, name, price, cat in cat_items:
            buttons.append([InlineKeyboardButton(
                text=f"{name} — {int(price)} ₽",
                callback_data=f"work:{code}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await message.answer(
            f"📅 **Дата: {date_str}**\n"
            f"📋 {worker_cats[0][2]} **{worker_cats[0][1]}**\n\n"
            f"Выберите работу:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.choosing_work)
    else:
        buttons = []
        for cat_code, cat_name, cat_emoji in worker_cats:
            count = len([i for i in items if i[3] == cat_code])
            buttons.append([InlineKeyboardButton(
                text=f"{cat_emoji} {cat_name} ({count})",
                callback_data=f"wcat:{cat_code}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await message.answer(
            f"📅 **Дата: {date_str}**\n\n"
            f"📂 Выберите категорию работ:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.choosing_category)


async def show_category_or_work(callback, state, chosen_date):
    """Показывает категории или работы после выбора даты"""
    items = get_price_list_for_worker(callback.from_user.id)
    worker_cats = get_worker_categories(callback.from_user.id)
    d = chosen_date.split("-")
    date_str = f"{d[2]}.{d[1]}.{d[0]}"

    if len(worker_cats) == 1:
        cat_code = worker_cats[0][0]
        cat_items = [i for i in items if i[3] == cat_code]
        buttons = []
        for code, name, price, cat in cat_items:
            buttons.append([InlineKeyboardButton(
                text=f"{name} — {int(price)} ₽",
                callback_data=f"work:{code}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await callback.message.edit_text(
            f"📅 **Дата: {date_str}**\n"
            f"📋 {worker_cats[0][2]} **{worker_cats[0][1]}**\n\n"
            f"Выберите работу:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.choosing_work)
    else:
        buttons = []
        for cat_code, cat_name, cat_emoji in worker_cats:
            count = len([i for i in items if i[3] == cat_code])
            buttons.append([InlineKeyboardButton(
                text=f"{cat_emoji} {cat_name} ({count})",
                callback_data=f"wcat:{cat_code}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await callback.message.edit_text(
            f"📅 **Дата: {date_str}**\n\n"
            f"📂 Выберите категорию работ:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.choosing_category)


@dp.callback_query(F.data == "wdate_back")
async def work_back_to_dates(callback: types.CallbackQuery, state: FSMContext):
    from datetime import timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)

    buttons = [
        [InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data=f"wdate:{today.isoformat()}"
        )],
        [InlineKeyboardButton(
            text=f"📅 Вчера ({yesterday.strftime('%d.%m')})",
            callback_data=f"wdate:{yesterday.isoformat()}"
        )],
        [InlineKeyboardButton(
            text="📅 Выбрать дату...",
            callback_data="wdate:custom"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ]
    await callback.message.edit_text(
        "📅 За какой день записать работу?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(WorkEntry.choosing_date)
    await callback.answer()


@dp.callback_query(F.data.startswith("wcat:"), WorkEntry.choosing_category)
async def work_category_chosen(callback: types.CallbackQuery, state: FSMContext):
    cat_code = callback.data.split(":")[1]
    items = get_price_list_for_worker(callback.from_user.id)
    cat_items = [i for i in items if i[3] == cat_code]
    if not cat_items:
        await callback.answer("Нет работ в категории", show_alert=True)
        return
    cats = get_worker_categories(callback.from_user.id)
    cat_info = next(((n, e) for c, n, e in cats if c == cat_code), ("", "📦"))

    data = await state.get_data()
    d = data["work_date"].split("-")
    date_str = f"{d[2]}.{d[1]}.{d[0]}"

    buttons = []
    for code, name, price, cat in cat_items:
        buttons.append([InlineKeyboardButton(
            text=f"{name} — {int(price)} ₽",
            callback_data=f"work:{code}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="wcat_back")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    await callback.message.edit_text(
        f"📅 **Дата: {date_str}**\n"
        f"{cat_info[1]} **{cat_info[0]}**\n\n"
        f"Выберите работу:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(WorkEntry.choosing_work)
    await callback.answer()


@dp.callback_query(F.data == "wcat_back", WorkEntry.choosing_work)
async def work_back_to_categories(callback: types.CallbackQuery, state: FSMContext):
    items = get_price_list_for_worker(callback.from_user.id)
    worker_cats = get_worker_categories(callback.from_user.id)

    data = await state.get_data()
    d = data["work_date"].split("-")
    date_str = f"{d[2]}.{d[1]}.{d[0]}"

    buttons = []
    for cat_code, cat_name, cat_emoji in worker_cats:
        count = len([i for i in items if i[3] == cat_code])
        buttons.append([InlineKeyboardButton(
            text=f"{cat_emoji} {cat_name} ({count})",
            callback_data=f"wcat:{cat_code}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    await callback.message.edit_text(
        f"📅 **Дата: {date_str}**\n\n"
        f"📂 Выберите категорию работ:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(WorkEntry.choosing_category)
    await callback.answer()


@dp.callback_query(F.data.startswith("work:"), WorkEntry.choosing_work)
async def work_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    items = get_price_list_for_worker(callback.from_user.id)
    info = next(((c, n, p) for c, n, p, cat in items if c == code), None)
    if not info:
        await callback.answer("Не найдено", show_alert=True)
        return
    await state.update_data(work_info={"code": info[0], "name": info[1], "price": info[2]})

    data = await state.get_data()
    d = data["work_date"].split("-")
    date_str = f"{d[2]}.{d[1]}.{d[0]}"

    await callback.message.edit_text(
        f"📅 **Дата: {date_str}**\n"
        f"**{info[1]}** ({int(info[2])} ₽/шт)\n\n"
        f"Введите количество:",
        parse_mode="Markdown"
    )
    await state.set_state(WorkEntry.entering_quantity)
    await callback.answer()


@dp.message(WorkEntry.entering_quantity)
async def quantity_entered(message: types.Message, state: FSMContext):
    try:
        qty = int(message.text)
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число!")
        return
    data = await state.get_data()
    info = data["work_info"]
    work_date = data.get("work_date", date.today().isoformat())

    total = add_work(message.from_user.id, info["code"], qty, info["price"], work_date)
    daily = get_daily_total(message.from_user.id, work_date)
    day_total = sum(r[3] for r in daily)

    d = work_date.split("-")
    date_str = f"{d[2]}.{d[1]}.{d[0]}"

    await message.answer(
        f"✅ **Записано!**\n\n"
        f"📅 Дата: **{date_str}**\n"
        f"📦 {info['name']} × {qty} = **{int(total)} ₽**\n"
        f"💰 За этот день: **{int(day_total)} ₽**",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

    # === Уведомление админу и менеджеру ===
    if message.from_user.id != ADMIN_ID:
        notify_text = (
            f"📬 **Новая запись!**\n\n"
            f"👤 {message.from_user.full_name}\n"
            f"📅 {date_str}\n"
            f"📦 {info['name']} × {qty} = **{int(total)} ₽**\n"
            f"💰 За этот день: **{int(day_total)} ₽**"
        )
        try:
            await bot.send_message(ADMIN_ID, notify_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Notify admin: {e}")

    if MANAGER_ID and message.from_user.id != MANAGER_ID:
        notify_text = (
            f"📬 **Новая запись!**\n\n"
            f"👤 {message.from_user.full_name}\n"
            f"📅 {date_str}\n"
            f"📦 {info['name']} × {qty} = **{int(total)} ₽**\n"
            f"💰 За этот день: **{int(day_total)} ₽**"
        )
        try:
            await bot.send_message(MANAGER_ID, notify_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Notify manager: {e}")

    await state.clear()


# ==================== МОИ ЗАПИСИ ====================

@dp.message(F.text == "📋 Мои записи")
async def my_entries(message: types.Message, state: FSMContext):
    from datetime import timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)

    buttons = [
        [InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data=f"viewdate:{today.isoformat()}"
        )],
        [InlineKeyboardButton(
            text=f"📅 Вчера ({yesterday.strftime('%d.%m')})",
            callback_data=f"viewdate:{yesterday.isoformat()}"
        )],
        [InlineKeyboardButton(
            text="📅 Выбрать дату...",
            callback_data="viewdate:custom"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="myback")]
    ]
    await message.answer(
        "📋 За какой день показать записи?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(ViewEntries.choosing_date)


@dp.callback_query(F.data.startswith("viewdate:"), ViewEntries.choosing_date)
async def view_date_chosen(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]

    if value == "custom":
        await callback.message.edit_text(
            "📅 Введите дату в формате **ДД.ММ.ГГГГ**\n\n"
            "Например: `25.05.2025`",
            parse_mode="Markdown"
        )
        await state.set_state(ViewEntries.entering_custom_date)
        await callback.answer()
        return

    await show_entries_for_date(callback.message, state,
                                 callback.from_user.id, value, edit=True)
    await callback.answer()


@dp.message(ViewEntries.entering_custom_date)
async def view_custom_date(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        parts = text.split(".")
        if len(parts) != 3:
            raise ValueError
        chosen = date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат!\n"
            "Введите дату как **ДД.ММ.ГГГГ**\n"
            "Например: `25.05.2025`",
            parse_mode="Markdown"
        )
        return

    await show_entries_for_date(message, state,
                                 message.from_user.id, chosen.isoformat(), edit=False)


async def show_entries_for_date(message, state, user_id, target_date, edit=False):
    """Показывает записи за выбранную дату"""
    entries = get_worker_entries_by_custom_date(user_id, target_date)

    d = target_date.split("-")
    date_str = f"{d[2]}.{d[1]}.{d[0]}"

    if not entries:
        text = f"📭 Нет записей за **{date_str}**"
        buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data="view_back")]]
        if edit:
            await message.edit_text(text, parse_mode="Markdown",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await state.set_state(WorkerDeleteEntry.choosing_entry)
        return

    text = f"📋 **Записи за {date_str}:**\n\n"
    buttons = []
    day_total = 0

    for entry_id, name, cat_name, cat_emoji, qty, price, total, created in entries:
        time_str = created[11:16] if len(created) > 16 else ""
        text += f"{cat_emoji} {name} × {int(qty)} = **{int(total)}₽** ({time_str})\n"
        day_total += total
        # Удалять можно только свои записи за сегодня
        if target_date == date.today().isoformat():
            buttons.append([InlineKeyboardButton(
                text=f"❌ {name} × {int(qty)} ({int(total)}₽)",
                callback_data=f"mydel:{entry_id}"
            )])

    text += f"\n💰 **Итого: {int(day_total)}₽**"

    if target_date == date.today().isoformat() and buttons:
        text += "\n\nНажмите чтобы удалить:"

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="view_back")])

    if edit:
        await message.edit_text(text, parse_mode="Markdown",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    await state.set_state(WorkerDeleteEntry.choosing_entry)


@dp.callback_query(F.data == "view_back")
async def view_entries_back(callback: types.CallbackQuery, state: FSMContext):
    from datetime import timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)

    buttons = [
        [InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data=f"viewdate:{today.isoformat()}"
        )],
        [InlineKeyboardButton(
            text=f"📅 Вчера ({yesterday.strftime('%d.%m')})",
            callback_data=f"viewdate:{yesterday.isoformat()}"
        )],
        [InlineKeyboardButton(
            text="📅 Выбрать дату...",
            callback_data="viewdate:custom"
        )],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="myback")]
    ]
    await callback.message.edit_text(
        "📋 За какой день показать записи?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(ViewEntries.choosing_date)
    await callback.answer()


# ==================== ЗАРАБОТОК ====================

@dp.message(F.text == "💰 За сегодня")
async def show_daily(message: types.Message):
    rows = get_daily_total(message.from_user.id)
    if not rows:
        await message.answer("📭 Сегодня нет записей.")
        return
    all_items = get_price_list()
    names = {i[0]: i[1] for i in all_items}
    text = f"📊 **{date.today().strftime('%d.%m.%Y')}:**\n\n"
    total = 0
    for code, qty, price, sub in rows:
        text += f"▫️ {names.get(code, code)}: {int(qty)}шт × {int(price)}₽ = **{int(sub)}₽**\n"
        total += sub
    text += f"\n💰 **Итого: {int(total)} ₽**"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📊 За месяц")
async def show_monthly(message: types.Message):
    today = date.today()
    rows = get_monthly_by_days(message.from_user.id, today.year, today.month)
    if not rows:
        await message.answer("📭 В этом месяце нет записей.")
        return
    MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    text = f"📊 **{MONTHS[today.month]} {today.year}:**\n\n"
    current_date = ""
    day_total = 0
    grand_total = 0
    work_days = 0
    for work_date, name, qty, price, subtotal in rows:
        if work_date != current_date:
            if current_date != "":
                text += f"   💰 За день: **{int(day_total)}₽**\n\n"
            parts = work_date.split("-")
            text += f"📅 **{parts[2]}.{parts[1]}.{parts[0]}:**\n"
            current_date = work_date
            day_total = 0
            work_days += 1
        text += f"   ▫️ {name} × {int(qty)} = **{int(subtotal)}₽**\n"
        day_total += subtotal
        grand_total += subtotal
    if current_date != "":
        text += f"   💰 За день: **{int(day_total)}₽**\n"
    text += f"\n━━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 Рабочих дней: **{work_days}**\n"
    text += f"💰 Итого за месяц: **{int(grand_total)} ₽**"
    await send_long_message(message, text)


# ==================== НАВИГАЦИЯ ПАНЕЛЕЙ ====================

@dp.message(F.text == "👑 Админ-панель")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer(
        "👑 **Админ-панель**\n\n"
        "📋 — Сводки и отчёты\n"
        "➕ — Добавить данные\n"
        "✏️ — Редактировать\n"
        "🗑 — Удалить\n"
        "📂 — Справочники",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "📊 Панель отчётов")
async def manager_panel(message: types.Message):
    if not is_manager(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer("📊 Панель отчётов", reply_markup=get_manager_keyboard())

@dp.message(F.text == "➕ Добавить")
async def menu_add(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("➕ **Добавить:**", parse_mode="Markdown",
                         reply_markup=get_add_keyboard())

@dp.message(F.text == "✏️ Редактировать")
async def menu_edit(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("✏️ **Редактировать:**", parse_mode="Markdown",
                         reply_markup=get_edit_keyboard())

@dp.message(F.text == "🗑 Удалить")
async def menu_delete(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🗑 **Удалить:**", parse_mode="Markdown",
                         reply_markup=get_delete_keyboard())

@dp.message(F.text == "📂 Справочники")
async def menu_info(message: types.Message):
    if not is_staff(message.from_user.id):
        return
    await message.answer("📂 **Справочники:**", parse_mode="Markdown",
                         reply_markup=get_info_keyboard())

@dp.message(F.text == "🔙 В админ-панель")
async def back_to_admin(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("👑 Админ-панель", reply_markup=get_admin_keyboard())
    elif is_manager(message.from_user.id):
        await message.answer("📊 Панель отчётов", reply_markup=get_manager_keyboard())

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню",
                         reply_markup=get_main_keyboard(message.from_user.id))


# ==================== КАТЕГОРИИ ====================

@dp.message(F.text == "➕ Категория")
async def add_cat_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Код категории (латиницей):")
    await state.set_state(AdminAddCategory.entering_code)

@dp.message(AdminAddCategory.entering_code)
async def add_cat_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip().lower())
    await message.answer("Название:")
    await state.set_state(AdminAddCategory.entering_name)

@dp.message(AdminAddCategory.entering_name)
async def add_cat_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Эмодзи (или - для 📦):")
    await state.set_state(AdminAddCategory.entering_emoji)

@dp.message(AdminAddCategory.entering_emoji)
async def add_cat_emoji(message: types.Message, state: FSMContext):
    emoji = message.text.strip()
    if emoji == "-":
        emoji = "📦"
    data = await state.get_data()
    add_category(data["code"], data["name"], emoji)
    await message.answer(
        f"✅ {emoji} **{data['name']}** (`{data['code']}`)",
        parse_mode="Markdown", reply_markup=get_add_keyboard()
    )
    await state.clear()

@dp.message(F.text == "📂 Категории")
async def show_cats(message: types.Message):
    if not is_staff(message.from_user.id):
        return
    cats = get_categories()
    if not cats:
        await message.answer("📂 Пусто.")
        return
    text = "📂 **Категории:**\n\n"
    for code, name, emoji in cats:
        workers = get_workers_in_category(code)
        w_str = ", ".join([w[1] for w in workers]) if workers else "—"
        items = [i for i in get_price_list() if i[3] == code]
        i_str = ", ".join([f"{i[1]}({int(i[2])}₽)" for i in items]) if items else "—"
        text += f"{emoji} **{name}** (`{code}`)\n👥 {w_str}\n📋 {i_str}\n\n"
    await send_long_message(message, text)


# ==================== ВИД РАБОТЫ ====================

@dp.message(F.text == "➕ Вид работы")
async def add_work_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    cats = get_categories()
    if not cats:
        await message.answer("⚠️ Сначала создайте категорию!")
        return
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"awc:{c}")] for c, n, e in cats]
    await message.answer("Категория:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAddWork.choosing_category)

@dp.callback_query(F.data.startswith("awc:"), AdminAddWork.choosing_category)
async def add_work_cat(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(category_code=callback.data.split(":")[1])
    await callback.message.edit_text("Код работы (латиницей):")
    await state.set_state(AdminAddWork.entering_code)
    await callback.answer()

@dp.message(AdminAddWork.entering_code)
async def add_work_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip().lower())
    await message.answer("Название:")
    await state.set_state(AdminAddWork.entering_name)

@dp.message(AdminAddWork.entering_name)
async def add_work_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Расценка (число):")
    await state.set_state(AdminAddWork.entering_price)

@dp.message(AdminAddWork.entering_price)
async def add_work_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', '.'))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    data = await state.get_data()
    add_price_item(data["code"], data["name"], price, data["category_code"])
    await message.answer(
        f"✅ `{data['code']}` — {data['name']} — {int(price)}₽",
        parse_mode="Markdown", reply_markup=get_add_keyboard()
    )
    await state.clear()


# ==================== РАБОТНИК ====================

@dp.message(F.text == "👤 Добавить работника")
async def add_worker_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Telegram ID (@userinfobot):")
    await state.set_state(AdminAddWorker.entering_id)

@dp.message(AdminAddWorker.entering_id)
async def add_worker_id(message: types.Message, state: FSMContext):
    try:
        tid = int(message.text)
    except ValueError:
        await message.answer("❌ Число!")
        return
    await state.update_data(worker_id=tid)
    await message.answer("Имя:")
    await state.set_state(AdminAddWorker.entering_name)

@dp.message(AdminAddWorker.entering_name)
async def add_worker_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    add_worker(data["worker_id"], message.text.strip())
    await message.answer(
        f"✅ **{message.text.strip()}** (`{data['worker_id']}`)\n"
        f"Назначьте категории: ✏️ Редактировать → 🔗",
        parse_mode="Markdown", reply_markup=get_add_keyboard()
    )
    await state.clear()


# ==================== СПИСКИ ====================

@dp.message(F.text == "👥 Работники")
async def show_workers(message: types.Message):
    if not is_staff(message.from_user.id):
        return
    workers = get_all_workers()
    if not workers:
        await message.answer("👥 Пусто.")
        return
    text = "👥 **Работники:**\n\n"
    for tid, name in workers:
        cats = get_worker_categories(tid)
        c_str = ", ".join([f"{c[2]}{c[1]}" for c in cats]) if cats else "❌ нет кат."
        text += f"▫️ **{name}** (`{tid}`)\n   {c_str}\n\n"
    await send_long_message(message, text)

@dp.message(F.text == "📄 Прайс-лист")
async def show_pricelist(message: types.Message):
    if not is_staff(message.from_user.id):
        return
    items = get_price_list()
    if not items:
        await message.answer("📄 Пусто.")
        return
    text = "📄 **Прайс-лист:**\n\n"
    cur = ""
    for code, name, price, cat_code, cat_name, cat_emoji in items:
        if cat_code != cur:
            cur = cat_code
            text += f"\n{cat_emoji} **{cat_name}:**\n"
        text += f"   ▫️ `{code}` — {name}: **{int(price)}₽**\n"
    await send_long_message(message, text)


# ==================== НАЗНАЧИТЬ / УБРАТЬ ====================

@dp.message(F.text == "🔗 Назначить кат.")
async def assign_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    workers = get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = []
    for tid, name in workers:
        cats = get_worker_categories(tid)
        c_str = ", ".join([f"{c[2]}{c[1]}" for c in cats]) if cats else "—"
        buttons.append([InlineKeyboardButton(text=f"{name} [{c_str}]", callback_data=f"asw:{tid}")])
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAssignCategory.choosing_worker)

@dp.callback_query(F.data.startswith("asw:"), AdminAssignCategory.choosing_worker)
async def assign_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    await state.update_data(worker_id=wid)
    cats = get_categories()
    current = {c[0] for c in get_worker_categories(wid)}
    available = [(c, n, e) for c, n, e in cats if c not in current]
    if not available:
        await callback.message.edit_text("✅ Все назначены!")
        await state.clear()
        await callback.answer()
        return
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"asc:{c}")] for c, n, e in available]
    await callback.message.edit_text("Категория:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAssignCategory.choosing_category)
    await callback.answer()

@dp.callback_query(F.data.startswith("asc:"), AdminAssignCategory.choosing_category)
async def assign_done(callback: types.CallbackQuery, state: FSMContext):
    cat = callback.data.split(":")[1]
    data = await state.get_data()
    assign_category_to_worker(data["worker_id"], cat)
    w = next((n for t, n in get_all_workers() if t == data["worker_id"]), "?")
    c = next((f"{e}{n}" for co, n, e in get_categories() if co == cat), "?")
    await callback.message.edit_text(f"✅ {w} → {c}")
    await state.clear()
    await callback.answer()

@dp.message(F.text == "🔓 Убрать кат.")
async def rmcat_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    buttons = []
    for tid, name in get_all_workers():
        cats = get_worker_categories(tid)
        if cats:
            c_str = ", ".join([f"{c[2]}{c[1]}" for c in cats])
            buttons.append([InlineKeyboardButton(text=f"{name} [{c_str}]", callback_data=f"rcw:{tid}")])
    if not buttons:
        await message.answer("⚠️ Ни у кого нет категорий.")
        return
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminRemoveCategory.choosing_worker)

@dp.callback_query(F.data.startswith("rcw:"), AdminRemoveCategory.choosing_worker)
async def rmcat_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    await state.update_data(worker_id=wid)
    cats = get_worker_categories(wid)
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"rcc:{c}")] for c, n, e in cats]
    await callback.message.edit_text("Убрать:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminRemoveCategory.choosing_category)
    await callback.answer()

@dp.callback_query(F.data.startswith("rcc:"), AdminRemoveCategory.choosing_category)
async def rmcat_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    remove_category_from_worker(data["worker_id"], callback.data.split(":")[1])
    await callback.message.edit_text("✅ Убрана!")
    await state.clear()
    await callback.answer()


# ==================== РАСЦЕНКА ====================

@dp.message(F.text == "✏️ Расценка")
async def edit_price_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    items = get_price_list()
    if not items:
        await message.answer("⚠️ Пусто.")
        return
    buttons = [[InlineKeyboardButton(text=f"{ce} {n} — {int(p)}₽", callback_data=f"ep:{c}")] for c, n, p, cc, cn, ce in items]
    await message.answer("Позиция:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminEditPrice.choosing_item)

@dp.callback_query(F.data.startswith("ep:"), AdminEditPrice.choosing_item)
async def edit_price_chosen(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(code=callback.data.split(":")[1])
    await callback.message.edit_text("Новая расценка:")
    await state.set_state(AdminEditPrice.entering_new_price)
    await callback.answer()

@dp.message(AdminEditPrice.entering_new_price)
async def edit_price_done(message: types.Message, state: FSMContext):
    try:
        p = float(message.text.replace(',', '.'))
        if p <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    data = await state.get_data()
    update_price(data["code"], p)
    await message.answer(f"✅ Расценка: **{int(p)}₽**",
                         parse_mode="Markdown", reply_markup=get_edit_keyboard())
    await state.clear()


# ==================== УДАЛЕНИЕ ====================

@dp.message(F.text == "🗑 Уд. категорию")
async def del_cat_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    cats = get_categories()
    if not cats:
        await message.answer("📂 Пусто.")
        return
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"dc:{c}")] for c, n, e in cats]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteCategory.choosing)

@dp.callback_query(F.data.startswith("dc:"), AdminDeleteCategory.choosing)
async def del_cat_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    info = next(((c, n, e) for c, n, e in get_categories() if c == code), None)
    if not info:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    await state.update_data(code=code, name=info[1], emoji=info[2])
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdc:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdc:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить {info[2]} **{info[1]}**?",
                                      parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteCategory.confirming)
    await callback.answer()

@dp.callback_query(F.data.startswith("cdc:"), AdminDeleteCategory.confirming)
async def del_cat_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        delete_category(data["code"])
        await callback.message.edit_text(f"✅ {data['emoji']} {data['name']} удалена!")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()

@dp.message(F.text == "🗑 Уд. работу")
async def del_work_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    items = get_price_list()
    if not items:
        await message.answer("📄 Пусто.")
        return
    buttons = [[InlineKeyboardButton(text=f"{ce} {n} — {int(p)}₽", callback_data=f"dw:{c}")] for c, n, p, cc, cn, ce in items]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWork.choosing)

@dp.callback_query(F.data.startswith("dw:"), AdminDeleteWork.choosing)
async def del_work_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    info = next(((c, n, p) for c, n, p, cc, cn, ce in get_price_list() if c == code), None)
    if not info:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    await state.update_data(code=code, name=info[1])
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdw:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdw:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить **{info[1]}** ({int(info[2])}₽)?",
                                      parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWork.confirming)
    await callback.answer()

@dp.callback_query(F.data.startswith("cdw:"), AdminDeleteWork.confirming)
async def del_work_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        full = delete_price_item_permanently(data["code"])
        msg = f"✅ **{data['name']}** удалён!" if full else f"✅ **{data['name']}** скрыт."
        await callback.message.edit_text(msg, parse_mode="Markdown")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()

@dp.message(F.text == "🗑 Уд. работника")
async def del_worker_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    buttons = []
    for tid, name in get_all_workers():
        if tid == ADMIN_ID:
            continue
        buttons.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=f"dwk:{tid}")])
    if not buttons:
        await message.answer("⚠️ Некого удалять.")
        return
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWorker.choosing)

@dp.callback_query(F.data.startswith("dwk:"), AdminDeleteWorker.choosing)
async def del_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    name = next((n for t, n in get_all_workers() if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=name)
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdwk:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdwk:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить **{name}**?",
                                      parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWorker.confirming)
    await callback.answer()

@dp.callback_query(F.data.startswith("cdwk:"), AdminDeleteWorker.confirming)
async def del_worker_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        delete_worker(data["worker_id"])
        await callback.message.edit_text(f"✅ **{data['worker_name']}** удалён!",
                                          parse_mode="Markdown")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "cdel")
async def cancel_del(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()


# ==================== СВОДКИ ====================

@dp.message(F.text == "📋 Сводка день")
async def summary_day(message: types.Message):
    if not is_staff(message.from_user.id):
        return
    summary = get_all_workers_daily_summary()
    text = f"📋 **{date.today().strftime('%d.%m.%Y')}:**\n\n"
    total = 0
    for tid, name, dt in summary:
        cats = get_worker_categories(tid)
        ce = "".join([c[2] for c in cats]) if cats else ""
        icon = '✅' if dt > 0 else '❌'
        text += f"{icon} {ce}{name}: **{int(dt)}₽**\n"
        total += dt
    text += f"\n💰 **Итого: {int(total)}₽**"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📋 Сводка месяц")
async def summary_month(message: types.Message):
    if not is_staff(message.from_user.id):
        return
    today = date.today()
    MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    details = get_admin_monthly_detailed_all(today.year, today.month)
    if not details:
        await message.answer("📭 Нет данных за этот месяц.")
        return

    text = f"📊 **{MONTHS[today.month].upper()} {today.year} — ПОЛНЫЙ ОТЧЁТ**\n\n"
    current_worker = None
    current_category = None
    current_date = None
    worker_total = 0
    cat_total = 0
    day_total = 0
    grand_total = 0
    worker_days = set()

    for tid, wname, cname, cemoji, wdate, pname, qty, price, total in details:
        if wname != current_worker:
            if current_date is not None:
                text += f"            💰 День: **{int(day_total)}₽**\n"
            if current_category is not None:
                text += f"      📊 Категория: **{int(cat_total)}₽**\n"
            if current_worker is not None:
                text += f"   ━━━━━━━━━━━━━━\n"
                text += f"   📊 Дней: **{len(worker_days)}** | 💰 Итого: **{int(worker_total)}₽**\n\n"
                grand_total += worker_total
            current_worker = wname
            current_category = None
            current_date = None
            worker_total = 0
            cat_total = 0
            day_total = 0
            worker_days = set()
            cats = get_worker_categories(tid)
            ce = "".join([c[2] for c in cats]) if cats else ""
            text += f"👤 **{wname}** {ce}\n"

        if cname != current_category:
            if current_date is not None:
                text += f"            💰 День: **{int(day_total)}₽**\n"
                day_total = 0
            if current_category is not None:
                text += f"      📊 Категория: **{int(cat_total)}₽**\n\n"
            current_category = cname
            current_date = None
            cat_total = 0
            text += f"   {cemoji} **{cname}:**\n"

        if wdate != current_date:
            if current_date is not None:
                text += f"            💰 День: **{int(day_total)}₽**\n"
            d = wdate.split("-")
            text += f"      📅 {d[2]}.{d[1]}:\n"
            current_date = wdate
            day_total = 0
            worker_days.add(wdate)

        text += f"         ▫️ {pname}: {int(qty)} × {int(price)} = **{int(total)}₽**\n"
        worker_total += total
        cat_total += total
        day_total += total

    if current_date is not None:
        text += f"            💰 День: **{int(day_total)}₽**\n"
    if current_category is not None:
        text += f"      📊 Категория: **{int(cat_total)}₽**\n"
    if current_worker is not None:
        text += f"   ━━━━━━━━━━━━━━\n"
        text += f"   📊 Дней: **{len(worker_days)}** | 💰 Итого: **{int(worker_total)}₽**\n\n"
        grand_total += worker_total

    text += f"━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 **ОБЩИЙ ФОНД: {int(grand_total)} ₽**"
    await send_long_message(message, text)


# ==================== ЗАПИСИ РАБОТНИКОВ ====================

@dp.message(F.text == "🔧 Записи работников")
async def admin_entries_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    workers = get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = [[InlineKeyboardButton(text=f"👤 {n}", callback_data=f"ae_w:{t}")] for t, n in workers]
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminManageEntries.choosing_worker)

@dp.callback_query(F.data.startswith("ae_w:"), AdminManageEntries.choosing_worker)
async def admin_entries_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    wname = next((n for t, n in get_all_workers() if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=wname)
    entries = get_worker_recent_entries(wid, limit=20)
    if not entries:
        await callback.message.edit_text(f"📭 У {wname} нет записей.")
        await state.clear()
        await callback.answer()
        return
    text = f"📋 **{wname}:**\n\n"
    buttons = []
    current_date = ""
    for eid, name, qty, price, total, wdate, created in entries:
        if wdate != current_date:
            parts = wdate.split("-")
            text += f"\n📅 **{parts[2]}.{parts[1]}.{parts[0]}:**\n"
            current_date = wdate
        text += f"   🔹 {name} × {int(qty)} = {int(total)}₽\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {name}×{int(qty)}={int(total)}₽ ({wdate})",
            callback_data=f"ae_e:{eid}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ae_back")])
    await callback.message.edit_text(text + "\n\nВыберите запись:",
                                      parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminManageEntries.viewing_entries)
    await callback.answer()

@dp.callback_query(F.data.startswith("ae_e:"), AdminManageEntries.viewing_entries)
async def admin_entry_chosen(callback: types.CallbackQuery, state: FSMContext):
    eid = int(callback.data.split(":")[1])
    entry = get_entry_by_id(eid)
    if not entry:
        await callback.answer("Не найдена", show_alert=True)
        return
    await state.update_data(entry_id=eid)
    parts = entry[5].split("-")
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить кол-во", callback_data="ae_act:edit")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="ae_act:delete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ae_act:back")]
    ]
    await callback.message.edit_text(
        f"📦 **{entry[1]}**\n\n"
        f"👤 {entry[7]}\n"
        f"📅 {parts[2]}.{parts[1]}.{parts[0]}\n"
        f"🔢 Кол-во: **{int(entry[2])}** шт\n"
        f"💵 Расценка: {int(entry[3])} ₽\n"
        f"💰 Сумма: **{int(entry[4])} ₽**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminManageEntries.choosing_action)
    await callback.answer()

@dp.callback_query(F.data.startswith("ae_act:"), AdminManageEntries.choosing_action)
async def admin_entry_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    if action == "edit":
        await callback.message.edit_text("Введите **правильное** количество:", parse_mode="Markdown")
        await state.set_state(AdminManageEntries.entering_new_quantity)
        await callback.answer()
    elif action == "delete":
        data = await state.get_data()
        entry = get_entry_by_id(data["entry_id"])
        buttons = [
            [InlineKeyboardButton(text="✅ Да!", callback_data="ae_del:yes")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="ae_del:no")]
        ]
        await callback.message.edit_text(
            f"⚠️ Удалить?\n📦 {entry[1]} × {int(entry[2])} = {int(entry[4])}₽",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(AdminManageEntries.confirming_delete)
        await callback.answer()
    elif action == "back":
        data = await state.get_data()
        entries = get_worker_recent_entries(data["worker_id"], limit=20)
        text = f"📋 **{data['worker_name']}:**\n\n"
        buttons = []
        current_date = ""
        for eid, name, qty, price, total, wdate, created in entries:
            if wdate != current_date:
                parts = wdate.split("-")
                text += f"\n📅 **{parts[2]}.{parts[1]}.{parts[0]}:**\n"
                current_date = wdate
            text += f"   🔹 {name} × {int(qty)} = {int(total)}₽\n"
            buttons.append([InlineKeyboardButton(
                text=f"📦 {name}×{int(qty)}={int(total)}₽",
                callback_data=f"ae_e:{eid}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ae_back")])
        await callback.message.edit_text(text + "\n\nВыберите:", parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await state.set_state(AdminManageEntries.viewing_entries)
        await callback.answer()

@dp.message(AdminManageEntries.entering_new_quantity)
async def admin_entry_new_qty(message: types.Message, state: FSMContext):
    try:
        new_qty = int(message.text)
        if new_qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Положительное число!")
        return
    data = await state.get_data()
    entry = get_entry_by_id(data["entry_id"])
    if not entry:
        await message.answer("❌ Не найдена.")
        await state.clear()
        return
    old_qty = entry[2]
    old_total = entry[4]
    new_total = new_qty * entry[3]
    update_entry_quantity(data["entry_id"], new_qty)
    await message.answer(
        f"✅ **Изменено!**\n\n📦 {entry[1]} ({entry[7]})\n"
        f"Было: {int(old_qty)}шт = {int(old_total)}₽\n"
        f"Стало: {new_qty}шт = **{int(new_total)}₽**",
        parse_mode="Markdown", reply_markup=get_edit_keyboard()
    )
    await state.clear()

@dp.callback_query(F.data.startswith("ae_del:"), AdminManageEntries.confirming_delete)
async def admin_entry_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        deleted = delete_entry_by_id(data["entry_id"])
        if deleted:
            await callback.message.edit_text(
                f"✅ Удалено: {deleted[1]} × {int(deleted[2])} = {int(deleted[3])}₽")
        else:
            await callback.message.edit_text("❌ Не найдена.")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "ae_back")
async def admin_entries_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Ок")
    await callback.answer()

# ==================== АВАНСЫ ====================

@dp.message(F.text == "💳 Выдать аванс")
async def advance_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    workers = get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = []
    for tid, name in workers:
        if tid == ADMIN_ID:
            continue
        earned = sum(r[3] for r in get_daily_total(tid)) if get_daily_total(tid) else 0
        today = date.today()
        adv_total = get_worker_advances_total(tid, today.year, today.month)
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name} (аванс: {int(adv_total)}₽)",
            callback_data=f"adv_w:{tid}"
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("👤 Кому выдать аванс?",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAdvance.choosing_worker)


@dp.callback_query(F.data.startswith("adv_w:"), AdminAdvance.choosing_worker)
async def advance_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    wname = next((n for t, n in get_all_workers() if t == wid), "?")
    today = date.today()
    earned = 0
    monthly = get_monthly_total(wid, today.year, today.month)
    for _, _, _, sub in monthly:
        earned += sub
    adv_total = get_worker_advances_total(wid, today.year, today.month)
    balance = earned - adv_total

    await state.update_data(worker_id=wid, worker_name=wname)
    await callback.message.edit_text(
        f"👤 **{wname}**\n\n"
        f"💰 Заработано: **{int(earned)}₽**\n"
        f"💳 Авансы: **{int(adv_total)}₽**\n"
        f"📊 Остаток: **{int(balance)}₽**\n\n"
        f"Введите сумму аванса:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminAdvance.entering_amount)
    await callback.answer()


@dp.message(AdminAdvance.entering_amount)
async def advance_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число!")
        return
    await state.update_data(amount=amount)
    await message.answer(
        f"💳 Сумма: **{int(amount)}₽**\n\n"
        f"Введите комментарий (или `-` чтобы пропустить):",
        parse_mode="Markdown"
    )
    await state.set_state(AdminAdvance.entering_comment)


@dp.message(AdminAdvance.entering_comment)
async def advance_comment(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    data = await state.get_data()
    add_advance(data["worker_id"], data["amount"], comment)

    today = date.today()
    earned = 0
    monthly = get_monthly_total(data["worker_id"], today.year, today.month)
    for _, _, _, sub in monthly:
        earned += sub
    adv_total = get_worker_advances_total(data["worker_id"], today.year, today.month)
    balance = earned - adv_total

    text = (
        f"✅ **Аванс выдан!**\n\n"
        f"👤 {data['worker_name']}\n"
        f"💳 Сумма: **{int(data['amount'])}₽**\n"
    )
    if comment:
        text += f"💬 {comment}\n"
    text += (
        f"\n📊 **Баланс:**\n"
        f"💰 Заработано: {int(earned)}₽\n"
        f"💳 Авансы: {int(adv_total)}₽\n"
        f"📊 Остаток: **{int(balance)}₽**"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_edit_keyboard())
    await state.clear()


@dp.message(F.text == "💳 Удалить аванс")
async def delete_advance_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    workers = get_all_workers()
    buttons = []
    today = date.today()
    for tid, name in workers:
        if tid == ADMIN_ID:
            continue
        advances = get_worker_advances(tid, today.year, today.month)
        if advances:
            total = sum(a[1] for a in advances)
            buttons.append([InlineKeyboardButton(
                text=f"👤 {name} ({int(total)}₽, {len(advances)} шт)",
                callback_data=f"dadv_w:{tid}"
            )])
    if not buttons:
        await message.answer("📭 Нет авансов за этот месяц.")
        return
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("👤 Выберите работника:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteAdvance.choosing_worker)


@dp.callback_query(F.data.startswith("dadv_w:"), AdminDeleteAdvance.choosing_worker)
async def del_advance_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    wname = next((n for t, n in get_all_workers() if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=wname)
    today = date.today()
    advances = get_worker_advances(wid, today.year, today.month)
    buttons = []
    for adv_id, amount, comment, adv_date, created in advances:
        d = adv_date.split("-")
        label = f"{d[2]}.{d[1]} — {int(amount)}₽"
        if comment:
            label += f" ({comment[:20]})"
        buttons.append([InlineKeyboardButton(
            text=f"💳 {label}",
            callback_data=f"dadv_a:{adv_id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="cdel")])
    await callback.message.edit_text(
        f"👤 **{wname}** — авансы:\n\nВыберите для удаления:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminDeleteAdvance.choosing_advance)
    await callback.answer()


@dp.callback_query(F.data.startswith("dadv_a:"), AdminDeleteAdvance.choosing_advance)
async def del_advance_chosen(callback: types.CallbackQuery, state: FSMContext):
    adv_id = int(callback.data.split(":")[1])
    await state.update_data(advance_id=adv_id)
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить!", callback_data="dadv_c:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="dadv_c:no")]
    ]
    await callback.message.edit_text(
        "⚠️ Удалить этот аванс?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminDeleteAdvance.confirming)
    await callback.answer()


@dp.callback_query(F.data.startswith("dadv_c:"), AdminDeleteAdvance.confirming)
async def del_advance_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        deleted = delete_advance(data["advance_id"])
        if deleted:
            await callback.message.edit_text(
                f"✅ Аванс {int(deleted[1])}₽ удалён!")
        else:
            await callback.message.edit_text("❌ Не найден.")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


@dp.message(F.text == "💰 Баланс работников")
async def show_balances(message: types.Message):
    if not is_staff(message.from_user.id):
        return
    today = date.today()
    MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

    text = f"💰 **Баланс — {MONTHS[today.month]} {today.year}**\n\n"
    workers = get_all_workers()
    grand_earned = 0
    grand_advance = 0

    for tid, name in workers:
        earned = 0
        monthly = get_monthly_total(tid, today.year, today.month)
        for _, _, _, sub in monthly:
            earned += sub
        adv_total = get_worker_advances_total(tid, today.year, today.month)
        balance = earned - adv_total

        if earned > 0 or adv_total > 0:
            icon = "✅" if balance >= 0 else "⚠️"
            text += (
                f"{icon} **{name}**\n"
                f"   💰 Заработано: {int(earned)}₽\n"
                f"   💳 Авансы: {int(adv_total)}₽\n"
                f"   📊 Остаток: **{int(balance)}₽**\n\n"
            )
            grand_earned += earned
            grand_advance += adv_total

    text += f"━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 Всего заработано: **{int(grand_earned)}₽**\n"
    text += f"💳 Всего авансов: **{int(grand_advance)}₽**\n"
    text += f"📊 Общий остаток: **{int(grand_earned - grand_advance)}₽**"

    await send_long_message(message, text)

# ==================== EXCEL ОТЧЁТЫ ====================

@dp.message(F.text == "📥 Отчёт месяц")
async def report_month(message: types.Message):
    if not is_staff(message.from_user.id):
        return
    await message.answer("⏳ Формирую...")
    try:
        today = date.today()
        fn = generate_monthly_report(today.year, today.month)
        await message.answer_document(FSInputFile(fn), caption="📊 Отчёт за месяц")
        os.remove(fn)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(F.text == "📥 Отчёт работник")
async def report_worker_start(message: types.Message, state: FSMContext):
    if not is_staff(message.from_user.id):
        return
    workers = get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = [[InlineKeyboardButton(text=f"👤 {n}", callback_data=f"rw:{t}")] for t, n in workers]
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(ReportWorker.choosing_worker)

@dp.callback_query(F.data.startswith("rw:"), ReportWorker.choosing_worker)
async def report_worker_gen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    name = next((n for t, n in get_all_workers() if t == wid), "Работник")
    await callback.message.edit_text("⏳ Формирую...")
    try:
        today = date.today()
        fn = generate_worker_report(wid, name, today.year, today.month)
        await callback.message.answer_document(FSInputFile(fn), caption=f"📊 {name}")
        os.remove(fn)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")
    await state.clear()
    await callback.answer()


# ==================== НАПОМИНАНИЯ ====================

async def send_evening_reminder():
    for tid, name in get_workers_without_records():
        try:
            await bot.send_message(tid, "🔔 Запишите работу за сегодня!")
        except Exception as e:
            logging.error(f"Reminder {name}: {e}")

async def send_late_reminder():
    for tid, name in get_workers_without_records():
        try:
            await bot.send_message(tid, "⚠️ Вы не записали работу! Нужно для зарплаты.")
        except Exception as e:
            logging.error(f"Late {name}: {e}")

async def send_admin_report():
    summary = get_all_workers_daily_summary()
    text = f"📊 **Итоги {date.today().strftime('%d.%m.%Y')}:**\n\n"
    total = 0
    for tid, name, dt in summary:
        icon = '✅' if dt > 0 else '❌'
        text += f"{icon} {name}: {int(dt)}₽\n"
        total += dt
    text += f"\n💰 Итого: {int(total)}₽"
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Admin report: {e}")


# ==================== БЭКАП ====================

@dp.message(F.text == "💾 Бэкап БД")
async def manual_backup(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await send_backup(message.from_user.id)


async def send_backup(chat_id=None):
    """Отправляет бэкап базы данных"""
    if chat_id is None:
        chat_id = ADMIN_ID

    import os as _os
    db_path = _os.path.join(
        _os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "."),
        "production.db"
    )

    if not _os.path.exists(db_path):
        try:
            await bot.send_message(chat_id, "❌ База данных не найдена.")
        except Exception:
            pass
        return

    try:
        today = date.today()
        caption = f"💾 Бэкап БД\n📅 {today.strftime('%d.%m.%Y %H:%M')}"
        await bot.send_document(
            chat_id,
            FSInputFile(db_path, filename=f"backup_{today.strftime('%Y%m%d')}.db"),
            caption=caption
        )
    except Exception as e:
        logging.error(f"Backup error: {e}")
        try:
            await bot.send_message(chat_id, f"❌ Ошибка бэкапа: {e}")
        except Exception:
            pass


async def auto_backup():
    """Автоматический ежедневный бэкап"""
    await send_backup(ADMIN_ID)

# ==================== ЗАПУСК ====================

async def main():
    init_db()
    scheduler.add_job(send_evening_reminder, "cron", hour=18, minute=0)
    scheduler.add_job(send_late_reminder, "cron", hour=20, minute=0)
    scheduler.add_job(send_admin_report, "cron", hour=21, minute=0)
    scheduler.add_job(auto_backup, "cron", hour=23, minute=0)
    scheduler.start()
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())