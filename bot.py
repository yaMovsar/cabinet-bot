import asyncio
import logging
import html
import os
from datetime import date, timedelta, datetime
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile, TelegramObject
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, ADMIN_ID, MANAGER_IDS
from database import (
    init_db, add_work, get_daily_total, get_monthly_total,
    get_workers_without_records, get_all_workers_daily_summary,
    get_all_workers_monthly_summary,
    get_price_list, get_price_list_for_worker,
    add_worker, worker_exists, delete_last_entry, add_price_item,
    update_price, get_all_workers,
    add_category, get_categories,
    assign_category_to_worker, remove_category_from_worker,
    get_worker_categories, get_workers_in_category,
    delete_category, delete_price_item_permanently, delete_worker,
    rename_worker,
    get_monthly_by_days,
    get_today_entries, get_worker_recent_entries,
    delete_entry_by_id, update_entry_quantity, get_entry_by_id,
    get_worker_monthly_details, get_all_workers_monthly_details,
    get_admin_monthly_detailed_all,
    add_advance, get_worker_advances, get_worker_advances_total,
    delete_advance, get_all_advances_monthly,
    get_worker_entries_by_custom_date,
    get_all_workers_balance, get_worker_full_stats,
    get_reminder_settings, update_reminder_settings,
    add_penalty, get_worker_penalties, get_worker_penalties_total,
    delete_penalty,
    DB_NAME
)
from reports import generate_monthly_report, generate_worker_report

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

MONTHS_RU = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


# ==================== УТИЛИТЫ ====================

def format_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return iso_date


def format_date_short(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m")
    except Exception:
        return iso_date


def parse_user_date(text: str):
    try:
        parts = text.strip().split(".")
        if len(parts) != 3:
            return None
        return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        return None


def make_date_picker(callback_prefix: str, cancel_callback: str = "cancel"):
    today = date.today()
    yesterday = today - timedelta(days=1)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data=f"{callback_prefix}:{today.isoformat()}"
        )],
        [InlineKeyboardButton(
            text=f"📅 Вчера ({yesterday.strftime('%d.%m')})",
            callback_data=f"{callback_prefix}:{yesterday.isoformat()}"
        )],
        [InlineKeyboardButton(
            text="📅 Выбрать дату...",
            callback_data=f"{callback_prefix}:custom"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_callback)]
    ])


def make_work_buttons(cat_items, columns=2):
    buttons = []
    row = []
    for code, name, price, cat in cat_items:
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


async def send_long_message(target, text, parse_mode=None):
    MAX_LEN = 4000
    if len(text) <= MAX_LEN:
        try:
            await target.answer(text, parse_mode=parse_mode)
        except Exception:
            await target.answer(text, parse_mode=None)
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
            try:
                await target.answer(part, parse_mode=parse_mode)
            except Exception:
                await target.answer(part, parse_mode=None)


# ==================== MIDDLEWARE ====================

class RoleMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user:
            uid = user.id
            data["is_admin"] = uid == ADMIN_ID
            data["is_manager"] = uid in MANAGER_IDS
            data["is_staff"] = uid == ADMIN_ID or uid in MANAGER_IDS
        else:
            data["is_admin"] = False
            data["is_manager"] = False
            data["is_staff"] = False
        return await handler(event, data)

dp.message.middleware(RoleMiddleware())
dp.callback_query.middleware(RoleMiddleware())


# ==================== ФИЛЬТРЫ ====================

class AdminFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id == ADMIN_ID


class StaffFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id == ADMIN_ID or message.from_user.id in MANAGER_IDS


# ==================== ERROR HANDLER ====================

@dp.error()
async def global_error_handler(event: types.ErrorEvent):
    if "message is not modified" in str(event.exception):
        return True
    logging.exception(f"Ошибка: {event.exception}")
    try:
        error_text = f"🚨 Ошибка бота:\n\n{type(event.exception).__name__}: {str(event.exception)[:500]}"
        await bot.send_message(ADMIN_ID, error_text)
    except Exception:
        pass
    update = event.update
    try:
        if update.message:
            await update.message.answer("❌ Произошла ошибка. Попробуйте позже или /cancel")
        elif update.callback_query:
            await update.callback_query.answer("❌ Ошибка. Попробуйте /cancel", show_alert=True)
    except Exception:
        pass


# ==================== СОСТОЯНИЯ ====================

class WorkEntry(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()
    choosing_category = State()
    choosing_work = State()
    entering_quantity = State()
    confirming_large = State()

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

class AdminRenameWorker(StatesGroup):
    choosing_worker = State()
    entering_name = State()

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

class AdminPenalty(StatesGroup):
    choosing_worker = State()
    entering_amount = State()
    entering_reason = State()

class AdminDeletePenalty(StatesGroup):
    choosing_worker = State()
    choosing_penalty = State()
    confirming = State()

class ViewEntries(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()

class AdminReminderSettings(StatesGroup):
    main_menu = State()
    entering_time = State()


# ==================== КЛАВИАТУРЫ ====================

def get_main_keyboard(user_id=None):
    buttons = [
        [KeyboardButton(text="📝 Записать работу"),
         KeyboardButton(text="📋 Мои записи")],
        [KeyboardButton(text="💰 За сегодня"),
         KeyboardButton(text="📊 За месяц")],
        [KeyboardButton(text="💳 Мой баланс")],
    ]
    if user_id and user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="👑 Админ-панель")])
    elif user_id and user_id in MANAGER_IDS:
        buttons.append([KeyboardButton(text="📊 Панель отчётов")])
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


# ==================== /start и /cancel ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, is_admin: bool, is_manager: bool, **kwargs):
    await state.clear()
    uid = message.from_user.id

    if is_admin:
        await add_worker(uid, message.from_user.full_name)
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n"
            "Вы — администратор.\n\n"
            "📌 Настройка:\n"
            "1. ➕ Добавить → Категория\n"
            "2. ➕ Добавить → Вид работы\n"
            "3. ➕ Добавить → Работника\n"
            "4. ✏️ Редактировать → Назначить кат."
        )
    elif is_manager:
        await add_worker(uid, message.from_user.full_name)
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n"
            "Вы — менеджер. Доступны отчёты и управление деньгами."
        )
    else:
        exists = await worker_exists(uid)
        if not exists:
            await message.answer("⛔ Вы не зарегистрированы. Обратитесь к администратору.")
            return
        text = (
            f"Привет, {message.from_user.first_name}! 👋\n"
            "Записывайте работу каждый день!"
        )
    await message.answer(text, reply_markup=get_main_keyboard(uid))


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.",
                         reply_markup=get_main_keyboard(message.from_user.id))


# ==================== ЗАПИСАТЬ РАБОТУ ====================

@dp.message(F.text == "📝 Записать работу")
async def start_work_entry(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list_for_worker(message.from_user.id)
    if not items:
        await message.answer("⚠️ Вам не назначены категории.")
        return
    await message.answer(
        "📅 За какой день записать работу?",
        reply_markup=make_date_picker("wdate", "cancel")
    )
    await state.set_state(WorkEntry.choosing_date)


@dp.callback_query(F.data.startswith("wdate:"), WorkEntry.choosing_date)
async def work_date_chosen(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "custom":
        await callback.message.edit_text(
            "📅 Введите дату в формате ДД.ММ.ГГГГ\n\nНапример: 25.05.2025"
        )
        await state.set_state(WorkEntry.entering_custom_date)
        await callback.answer()
        return
    await state.update_data(work_date=value)
    await show_category_or_work(callback, state, value)
    await callback.answer()


@dp.message(WorkEntry.entering_custom_date)
async def custom_date_entered(message: types.Message, state: FSMContext):
    chosen = parse_user_date(message.text)
    if not chosen:
        await message.answer("❌ Неверный формат!\nВведите дату как ДД.ММ.ГГГГ\nНапример: 25.05.2025")
        return
    if chosen > date.today():
        await message.answer("❌ Нельзя записать на будущую дату!")
        return
    if chosen < date.today() - timedelta(days=90):
        await message.answer("❌ Нельзя записать дату старше 90 дней!")
        return

    chosen_date = chosen.isoformat()
    await state.update_data(work_date=chosen_date)

    items = await get_price_list_for_worker(message.from_user.id)
    worker_cats = await get_worker_categories(message.from_user.id)

    if len(worker_cats) == 1:
        cat_code = worker_cats[0][0]
        cat_items = [i for i in items if i[3] == cat_code]
        buttons = make_work_buttons(cat_items)
        buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await message.answer(
            f"📅 Дата: {format_date(chosen_date)}\n"
            f"📋 {worker_cats[0][2]} {worker_cats[0][1]}\n\nВыберите работу:",
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
            f"📅 Дата: {format_date(chosen_date)}\n\n📂 Выберите категорию работ:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.choosing_category)


async def show_category_or_work(callback, state, chosen_date):
    items = await get_price_list_for_worker(callback.from_user.id)
    worker_cats = await get_worker_categories(callback.from_user.id)

    if len(worker_cats) == 1:
        cat_code = worker_cats[0][0]
        cat_items = [i for i in items if i[3] == cat_code]
        buttons = make_work_buttons(cat_items)
        buttons.append([InlineKeyboardButton(text="🔙 К датам", callback_data="wdate_back")])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
        await callback.message.edit_text(
            f"📅 Дата: {format_date(chosen_date)}\n"
            f"📋 {worker_cats[0][2]} {worker_cats[0][1]}\n\nВыберите работу:",
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
            f"📅 Дата: {format_date(chosen_date)}\n\n📂 Выберите категорию работ:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.choosing_category)


@dp.callback_query(F.data == "wdate_back")
async def work_back_to_dates(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📅 За какой день записать работу?",
        reply_markup=make_date_picker("wdate", "cancel")
    )
    await state.set_state(WorkEntry.choosing_date)
    await callback.answer()


@dp.callback_query(F.data.startswith("wcat:"), WorkEntry.choosing_category)
async def work_category_chosen(callback: types.CallbackQuery, state: FSMContext):
    cat_code = callback.data.split(":")[1]
    items = await get_price_list_for_worker(callback.from_user.id)
    cat_items = [i for i in items if i[3] == cat_code]
    if not cat_items:
        await callback.answer("Нет работ в категории", show_alert=True)
        return
    cats = await get_worker_categories(callback.from_user.id)
    cat_info = next(((n, e) for c, n, e in cats if c == cat_code), ("", "📦"))
    data = await state.get_data()
    buttons = make_work_buttons(cat_items)
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="wcat_back")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    await callback.message.edit_text(
        f"📅 Дата: {format_date(data['work_date'])}\n"
        f"{cat_info[1]} {cat_info[0]}\n\nВыберите работу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(WorkEntry.choosing_work)
    await callback.answer()


@dp.callback_query(F.data == "wcat_back", WorkEntry.choosing_work)
async def work_back_to_categories(callback: types.CallbackQuery, state: FSMContext):
    items = await get_price_list_for_worker(callback.from_user.id)
    worker_cats = await get_worker_categories(callback.from_user.id)
    data = await state.get_data()
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
        f"📅 Дата: {format_date(data['work_date'])}\n\n📂 Выберите категорию работ:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(WorkEntry.choosing_category)
    await callback.answer()


@dp.callback_query(F.data.startswith("work:"), WorkEntry.choosing_work)
async def work_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    items = await get_price_list_for_worker(callback.from_user.id)
    info = next(((c, n, p) for c, n, p, cat in items if c == code), None)
    if not info:
        await callback.answer("Не найдено", show_alert=True)
        return
    await state.update_data(work_info={"code": info[0], "name": info[1], "price": info[2]})
    data = await state.get_data()
    await callback.message.edit_text(
        f"📅 Дата: {format_date(data['work_date'])}\n"
        f"{info[1]} ({int(info[2])} руб/шт)\n\nВведите количество:"
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
    total = qty * info["price"]

    if total > 10000:
        await state.update_data(quantity=qty)
        buttons = [
            [InlineKeyboardButton(text="✅ Да, записать!", callback_data="confirm_large:yes")],
            [InlineKeyboardButton(text="✏️ Изменить количество", callback_data="confirm_large:edit")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_large:cancel")]
        ]
        await message.answer(
            f"⚠️ Внимание! Большая сумма!\n\n"
            f"📅 Дата: {format_date(data.get('work_date', date.today().isoformat()))}\n"
            f"📦 {info['name']} x {qty} = {int(total)} руб\n\nВсё верно?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkEntry.confirming_large)
        return

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
        await callback.message.edit_text("Введите правильное количество:")
        await state.set_state(WorkEntry.entering_quantity)
    elif action == "cancel":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()
    await callback.answer()


async def save_work_entry(message, state, qty, user=None):
    if user is None:
        user = message.from_user

    data = await state.get_data()
    info = data["work_info"]
    work_date = data.get("work_date", date.today().isoformat())

    total = await add_work(user.id, info["code"], qty, info["price"], work_date)
    daily = await get_daily_total(user.id, work_date)
    day_total = sum(r[3] for r in daily)

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Записать ещё", callback_data="write_more")],
    ])

    await message.answer(
        f"✅ Записано!\n\n"
        f"📅 Дата: {format_date(work_date)}\n"
        f"📦 {info['name']} x {qty} = {int(total)} руб\n"
        f"💰 За этот день: {int(day_total)} руб",
        reply_markup=buttons
    )

    if user.id != ADMIN_ID:
        notify_text = (
            f"📬 Новая запись!\n\n"
            f"👤 {user.full_name}\n"
            f"📅 {format_date(work_date)}\n"
            f"📦 {info['name']} x {qty} = {int(total)} руб\n"
            f"💰 За этот день: {int(day_total)} руб"
        )
        try:
            await bot.send_message(ADMIN_ID, notify_text)
        except Exception as e:
            logging.error(f"Notify admin: {e}")
        for mgr_id in MANAGER_IDS:
            try:
                await bot.send_message(mgr_id, notify_text)
            except Exception as e:
                logging.error(f"Notify manager {mgr_id}: {e}")

    await state.clear()


@dp.callback_query(F.data == "write_more")
async def write_more(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    items = await get_price_list_for_worker(callback.from_user.id)
    if not items:
        await callback.answer("⚠️ Вам не назначены категории.", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "📅 За какой день записать работу?",
        reply_markup=make_date_picker("wdate", "cancel")
    )
    await state.set_state(WorkEntry.choosing_date)
    await callback.answer()


@dp.callback_query(F.data == "cancel")
async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


# ==================== МОЙ БАЛАНС ====================

@dp.message(F.text == "💳 Мой баланс")
async def my_balance(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    today = date.today()
    stats = await get_worker_full_stats(uid, today.year, today.month)
    advances = await get_worker_advances(uid, today.year, today.month)
    penalties = await get_worker_penalties(uid, today.year, today.month)

    text = f"💰 Мой баланс — {MONTHS_RU[today.month]} {today.year}\n\n"
    text += f"💰 Заработано: {int(stats['earned'])} руб\n"
    text += f"📅 Рабочих дней: {stats['work_days']}\n"
    text += f"💳 Авансы: {int(stats['advances'])} руб\n"
    text += f"⚠️ Штрафы: {int(stats['penalties'])} руб\n"
    text += f"📊 Остаток: {int(stats['balance'])} руб\n"

    if advances:
        text += f"\n📋 Авансы:\n"
        for adv_id, amount, comment, adv_date, created in advances:
            text += f"   ▫️ {format_date(adv_date)}: {int(amount)} руб"
            if comment:
                text += f" ({comment})"
            text += "\n"

    if penalties:
        text += f"\n⚠️ Штрафы:\n"
        for pen_id, amount, reason, pen_date, created in penalties:
            text += f"   ▫️ {format_date(pen_date)}: {int(amount)} руб"
            if reason:
                text += f" ({reason})"
            text += "\n"

    if stats['work_days'] > 0:
        avg = stats['earned'] / stats['work_days']
        text += f"\n📊 Среднее в день: {int(avg)} руб"

    await message.answer(text)


# ==================== МОИ ЗАПИСИ ====================

@dp.message(F.text == "📋 Мои записи")
async def my_entries(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📋 За какой день показать записи?",
        reply_markup=make_date_picker("viewdate", "myback")
    )
    await state.set_state(ViewEntries.choosing_date)


@dp.callback_query(F.data.startswith("viewdate:"), ViewEntries.choosing_date)
async def view_date_chosen(callback: types.CallbackQuery, state: FSMContext):
    value = callback.data.split(":", 1)[1]
    if value == "custom":
        await callback.message.edit_text(
            "📅 Введите дату в формате ДД.ММ.ГГГГ\n\nНапример: 25.05.2025"
        )
        await state.set_state(ViewEntries.entering_custom_date)
        await callback.answer()
        return
    await show_entries_for_date(callback.message, state,
                                 callback.from_user.id, value, edit=True)
    await callback.answer()


@dp.message(ViewEntries.entering_custom_date)
async def view_custom_date(message: types.Message, state: FSMContext):
    chosen = parse_user_date(message.text)
    if not chosen:
        await message.answer("❌ Неверный формат!\nВведите дату как ДД.ММ.ГГГГ\nНапример: 25.05.2025")
        return
    await show_entries_for_date(message, state,
                                 message.from_user.id, chosen.isoformat(), edit=False)


async def show_entries_for_date(message, state, user_id, target_date, edit=False):
    entries = await get_worker_entries_by_custom_date(user_id, target_date)
    date_str = format_date(target_date)

    if not entries:
        text = f"📭 Нет записей за {date_str}"
        buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data="view_back")]]
        if edit:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await state.set_state(WorkerDeleteEntry.choosing_entry)
        return

    text = f"📋 Записи за {date_str}:\n\n"
    buttons = []
    day_total = 0

    for entry_id, name, cat_name, cat_emoji, qty, price, total, created in entries:
        time_str = created[11:16] if len(created) > 16 else ""
        text += f"{cat_emoji} {name} x {int(qty)} = {int(total)} руб ({time_str})\n"
        day_total += total
        if target_date == date.today().isoformat():
            buttons.append([InlineKeyboardButton(
                text=f"❌ {name} x {int(qty)} ({int(total)} руб)",
                callback_data=f"mydel:{entry_id}"
            )])

    text += f"\n💰 Итого: {int(day_total)} руб"
    if target_date == date.today().isoformat() and buttons:
        text += "\n\nНажмите чтобы удалить:"

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="view_back")])

    if edit:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(WorkerDeleteEntry.choosing_entry)


@dp.callback_query(F.data == "view_back")
async def view_entries_back(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📋 За какой день показать записи?",
        reply_markup=make_date_picker("viewdate", "myback")
    )
    await state.set_state(ViewEntries.choosing_date)
    await callback.answer()


@dp.callback_query(F.data.startswith("mydel:"), WorkerDeleteEntry.choosing_entry)
async def my_entry_chosen(callback: types.CallbackQuery, state: FSMContext):
    entry_id = int(callback.data.split(":")[1])
    entry = await get_entry_by_id(entry_id)
    if not entry:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    if entry[6] != callback.from_user.id:
        await callback.answer("Не ваша запись!", show_alert=True)
        await state.clear()
        return
    await state.update_data(entry_id=entry_id, entry_name=entry[1],
                            entry_qty=entry[2], entry_total=entry[4])
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить!", callback_data="myconf:yes")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="myconf:no")]
    ]
    await callback.message.edit_text(
        f"⚠️ Удалить?\n\n📦 {entry[1]} x {int(entry[2])} = {int(entry[4])} руб",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(WorkerDeleteEntry.confirming)
    await callback.answer()


@dp.callback_query(F.data.startswith("myconf:"), WorkerDeleteEntry.confirming)
async def my_entry_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        await delete_entry_by_id(data["entry_id"])
        await callback.message.edit_text(
            f"✅ Удалено: {data['entry_name']} x {int(data['entry_qty'])}")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "myback")
async def my_entries_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Ок")
    await callback.answer()


# ==================== ЗАРАБОТОК ====================

@dp.message(F.text == "💰 За сегодня")
async def show_daily(message: types.Message, state: FSMContext):
    await state.clear()
    rows = await get_daily_total(message.from_user.id)
    if not rows:
        await message.answer("📭 Сегодня нет записей.")
        return
    all_items = await get_price_list()
    names = {i[0]: i[1] for i in all_items}
    text = f"📊 {date.today().strftime('%d.%m.%Y')}:\n\n"
    total = 0
    for code, qty, price, sub in rows:
        text += f"▫️ {names.get(code, code)}: {int(qty)}шт x {int(price)} руб = {int(sub)} руб\n"
        total += sub
    text += f"\n💰 Итого: {int(total)} руб"
    await message.answer(text)


@dp.message(F.text == "📊 За месяц")
async def show_monthly(message: types.Message, state: FSMContext):
    await state.clear()
    today = date.today()
    rows = await get_monthly_by_days(message.from_user.id, today.year, today.month)
    if not rows:
        await message.answer("📭 В этом месяце нет записей.")
        return
    text = f"📊 {MONTHS_RU[today.month]} {today.year}:\n\n"
    current_date = ""
    day_total = 0
    grand_total = 0
    work_days = 0
    for work_date, name, qty, price, subtotal in rows:
        if work_date != current_date:
            if current_date != "":
                text += f"   💰 За день: {int(day_total)} руб\n\n"
            text += f"📅 {format_date(work_date)}:\n"
            current_date = work_date
            day_total = 0
            work_days += 1
        text += f"   ▫️ {name} x {int(qty)} = {int(subtotal)} руб\n"
        day_total += subtotal
        grand_total += subtotal
    if current_date != "":
        text += f"   💰 За день: {int(day_total)} руб\n"
    text += f"\n━━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 Рабочих дней: {work_days}\n"
    text += f"💰 Итого за месяц: {int(grand_total)} руб"
    await send_long_message(message, text)


# ==================== НАВИГАЦИЯ ====================

@dp.message(F.text == "👑 Админ-панель")
async def admin_panel(message: types.Message, state: FSMContext, is_admin: bool, **kwargs):
    if not is_admin:
        await message.answer("⛔ Нет доступа.")
        return
    await state.clear()
    await message.answer(
        "👑 Админ-панель\n\n"
        "📋 — Сводки и отчёты\n"
        "➕ — Добавить данные\n"
        "✏️ — Редактировать\n"
        "🗑 — Удалить\n"
        "📂 — Справочники\n"
        "💰 — Деньги, авансы, штрафы\n"
        "⏰ — Настройка напоминаний",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "📊 Панель отчётов")
async def manager_panel(message: types.Message, state: FSMContext, is_manager: bool, **kwargs):
    if not is_manager:
        await message.answer("⛔ Нет доступа.")
        return
    await state.clear()
    await message.answer("📊 Панель отчётов", reply_markup=get_manager_keyboard())

@dp.message(F.text == "➕ Добавить", AdminFilter())
async def menu_add(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("➕ Добавить:", reply_markup=get_add_keyboard())

@dp.message(F.text == "✏️ Редактировать", AdminFilter())
async def menu_edit(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("✏️ Редактировать:", reply_markup=get_edit_keyboard())

@dp.message(F.text == "🗑 Удалить", AdminFilter())
async def menu_delete(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🗑 Удалить:", reply_markup=get_delete_keyboard())

@dp.message(F.text == "📂 Справочники", StaffFilter())
async def menu_info(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📂 Справочники:", reply_markup=get_info_keyboard())

@dp.message(F.text == "💰 Деньги", StaffFilter())
async def menu_money(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "💰 Раздел Деньги\n\n💳 — Авансы\n⚠️ — Штрафы\n💰 — Баланс\n📊 — Заработок\n🏆 — Рейтинг",
        reply_markup=get_money_keyboard()
    )

@dp.message(F.text == "🔙 В админ-панель")
async def back_to_admin(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Админ-панель", reply_markup=get_admin_keyboard())
    elif message.from_user.id in MANAGER_IDS:
        await message.answer("📊 Панель отчётов", reply_markup=get_manager_keyboard())

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню",
                         reply_markup=get_main_keyboard(message.from_user.id))


# ==================== КАТЕГОРИИ ====================

@dp.message(F.text == "➕ Категория", AdminFilter())
async def add_cat_start(message: types.Message, state: FSMContext):
    await state.clear()
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
    await add_category(data["code"], data["name"], emoji)
    await message.answer(f"✅ {emoji} {data['name']} ({data['code']})", reply_markup=get_add_keyboard())
    await state.clear()

@dp.message(F.text == "📂 Категории", StaffFilter())
async def show_cats(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
    if not cats:
        await message.answer("📂 Пусто.")
        return
    text = "📂 Категории:\n\n"
    for code, name, emoji in cats:
        workers = await get_workers_in_category(code)
        w_str = ", ".join([w[1] for w in workers]) if workers else "—"
        all_items = await get_price_list()
        items = [i for i in all_items if i[3] == code]
        i_str = ", ".join([f"{i[1]}({int(i[2])} руб)" for i in items]) if items else "—"
        text += f"{emoji} {name} ({code})\n👥 {w_str}\n📋 {i_str}\n\n"
    await send_long_message(message, text)


# ==================== ВИД РАБОТЫ ====================

@dp.message(F.text == "➕ Вид работы", AdminFilter())
async def add_work_start(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
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
    await add_price_item(data["code"], data["name"], price, data["category_code"])
    await message.answer(f"✅ {data['code']} — {data['name']} — {int(price)} руб", reply_markup=get_add_keyboard())
    await state.clear()


# ==================== РАБОТНИК ====================

@dp.message(F.text == "👤 Добавить работника", AdminFilter())
async def add_worker_start(message: types.Message, state: FSMContext):
    await state.clear()
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
    await add_worker(data["worker_id"], message.text.strip())
    await message.answer(
        f"✅ {message.text.strip()} ({data['worker_id']})\n"
        f"Назначьте категории: ✏️ Редактировать → 🔗",
        reply_markup=get_add_keyboard()
    )
    await state.clear()


# ==================== ПЕРЕИМЕНОВАТЬ РАБОТНИКА ====================

@dp.message(F.text == "✏️ Переименовать", AdminFilter())
async def rename_worker_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = [[InlineKeyboardButton(text=f"👤 {n} ({t})", callback_data=f"rnw:{t}")] for t, n in workers]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Кого переименовать?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminRenameWorker.choosing_worker)

@dp.callback_query(F.data.startswith("rnw:"), AdminRenameWorker.choosing_worker)
async def rename_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    old_name = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, old_name=old_name)
    await callback.message.edit_text(
        f"👤 Текущее имя: {old_name}\n\nВведите новое имя:"
    )
    await state.set_state(AdminRenameWorker.entering_name)
    await callback.answer()

@dp.message(AdminRenameWorker.entering_name)
async def rename_worker_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_name = message.text.strip()
    await rename_worker(data["worker_id"], new_name)
    await message.answer(
        f"✅ Переименовано!\n\nБыло: {data['old_name']}\nСтало: {new_name}",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()


# ==================== СПИСКИ ====================

@dp.message(F.text == "👥 Работники", StaffFilter())
async def show_workers(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("👥 Пусто.")
        return
    text = "👥 Работники:\n\n"
    for tid, name in workers:
        cats = await get_worker_categories(tid)
        c_str = ", ".join([f"{c[2]}{c[1]}" for c in cats]) if cats else "нет кат."
        text += f"▫️ {name} ({tid})\n   {c_str}\n\n"
    await send_long_message(message, text)

@dp.message(F.text == "📄 Прайс-лист", StaffFilter())
async def show_pricelist(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("📄 Пусто.")
        return
    text = "📄 Прайс-лист:\n\n"
    cur = ""
    for code, name, price, cat_code, cat_name, cat_emoji in items:
        if cat_code != cur:
            cur = cat_code
            text += f"\n{cat_emoji} {cat_name}:\n"
        text += f"   ▫️ {code} — {name}: {int(price)} руб\n"
    await send_long_message(message, text)


# ==================== НАЗНАЧИТЬ / УБРАТЬ ====================

@dp.message(F.text == "🔗 Назначить кат.", AdminFilter())
async def assign_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = []
    for tid, name in workers:
        cats = await get_worker_categories(tid)
        c_str = ", ".join([f"{c[2]}{c[1]}" for c in cats]) if cats else "—"
        buttons.append([InlineKeyboardButton(text=f"{name} [{c_str}]", callback_data=f"asw:{tid}")])
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAssignCategory.choosing_worker)

@dp.callback_query(F.data.startswith("asw:"), AdminAssignCategory.choosing_worker)
async def assign_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    await state.update_data(worker_id=wid)
    cats = await get_categories()
    current = {c[0] for c in await get_worker_categories(wid)}
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
    await assign_category_to_worker(data["worker_id"], cat)
    workers = await get_all_workers()
    w = next((n for t, n in workers if t == data["worker_id"]), "?")
    cats = await get_categories()
    c = next((f"{e}{n}" for co, n, e in cats if co == cat), "?")
    await callback.message.edit_text(f"✅ {w} -> {c}")
    await state.clear()
    await callback.answer()

@dp.message(F.text == "🔓 Убрать кат.", AdminFilter())
async def rmcat_start(message: types.Message, state: FSMContext):
    await state.clear()
    buttons = []
    for tid, name in await get_all_workers():
        cats = await get_worker_categories(tid)
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
    cats = await get_worker_categories(wid)
    buttons = [[InlineKeyboardButton(text=f"{e} {n}", callback_data=f"rcc:{c}")] for c, n, e in cats]
    await callback.message.edit_text("Убрать:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminRemoveCategory.choosing_category)
    await callback.answer()

@dp.callback_query(F.data.startswith("rcc:"), AdminRemoveCategory.choosing_category)
async def rmcat_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await remove_category_from_worker(data["worker_id"], callback.data.split(":")[1])
    await callback.message.edit_text("✅ Убрана!")
    await state.clear()
    await callback.answer()


# ==================== РАСЦЕНКА ====================

@dp.message(F.text == "✏️ Расценка", AdminFilter())
async def edit_price_start(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("⚠️ Пусто.")
        return
    buttons = [[InlineKeyboardButton(text=f"{ce} {n} — {int(p)} руб",
                callback_data=f"ep:{c}")] for c, n, p, cc, cn, ce in items]
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
    await update_price(data["code"], p)
    await message.answer(f"✅ Расценка: {int(p)} руб", reply_markup=get_edit_keyboard())
    await state.clear()


# ==================== УДАЛЕНИЕ ====================

@dp.message(F.text == "🗑 Уд. категорию", AdminFilter())
async def del_cat_start(message: types.Message, state: FSMContext):
    await state.clear()
    cats = await get_categories()
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
    cats = await get_categories()
    info = next(((c, n, e) for c, n, e in cats if c == code), None)
    if not info:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    await state.update_data(code=code, name=info[1], emoji=info[2])
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdc:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdc:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить {info[2]} {info[1]}?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteCategory.confirming)
    await callback.answer()

@dp.callback_query(F.data.startswith("cdc:"), AdminDeleteCategory.confirming)
async def del_cat_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        await delete_category(data["code"])
        await callback.message.edit_text(f"✅ {data['emoji']} {data['name']} удалена!")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()

@dp.message(F.text == "🗑 Уд. работу", AdminFilter())
async def del_work_start(message: types.Message, state: FSMContext):
    await state.clear()
    items = await get_price_list()
    if not items:
        await message.answer("📄 Пусто.")
        return
    buttons = [[InlineKeyboardButton(text=f"{ce} {n} — {int(p)} руб",
                callback_data=f"dw:{c}")] for c, n, p, cc, cn, ce in items]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("Удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWork.choosing)

@dp.callback_query(F.data.startswith("dw:"), AdminDeleteWork.choosing)
async def del_work_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    items = await get_price_list()
    info = next(((c, n, p) for c, n, p, cc, cn, ce in items if c == code), None)
    if not info:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    await state.update_data(code=code, name=info[1])
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdw:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdw:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить {info[1]} ({int(info[2])} руб)?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWork.confirming)
    await callback.answer()

@dp.callback_query(F.data.startswith("cdw:"), AdminDeleteWork.confirming)
async def del_work_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        full = await delete_price_item_permanently(data["code"])
        msg = f"✅ {data['name']} удалён!" if full else f"✅ {data['name']} скрыт."
        await callback.message.edit_text(msg)
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()

@dp.message(F.text == "🗑 Уд. работника", AdminFilter())
async def del_worker_start(message: types.Message, state: FSMContext):
    await state.clear()
    buttons = []
    for tid, name in await get_all_workers():
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
    workers = await get_all_workers()
    name = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=name)
    buttons = [
        [InlineKeyboardButton(text="✅ Да!", callback_data="cdwk:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="cdwk:no")]
    ]
    await callback.message.edit_text(f"⚠️ Удалить {name}?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteWorker.confirming)
    await callback.answer()

@dp.callback_query(F.data.startswith("cdwk:"), AdminDeleteWorker.confirming)
async def del_worker_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        await delete_worker(data["worker_id"])
        await callback.message.edit_text(f"✅ {data['worker_name']} удалён!")
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

@dp.message(F.text == "📋 Сводка день", StaffFilter())
async def summary_day(message: types.Message, state: FSMContext):
    await state.clear()
    summary = await get_all_workers_daily_summary()
    text = f"📋 {date.today().strftime('%d.%m.%Y')}:\n\n"
    total = 0
    for tid, name, dt in summary:
        cats = await get_worker_categories(tid)
        ce = "".join([c[2] for c in cats]) if cats else ""
        icon = '✅' if dt > 0 else '❌'
        text += f"{icon} {ce}{name}: {int(dt)} руб\n"
        total += dt
    text += f"\n💰 Итого: {int(total)} руб"
    await message.answer(text)

@dp.message(F.text == "📋 Сводка месяц", StaffFilter())
async def summary_month(message: types.Message, state: FSMContext):
    await state.clear()
    today = date.today()
    details = await get_admin_monthly_detailed_all(today.year, today.month)
    if not details:
        await message.answer("📭 Нет данных за этот месяц.")
        return

    text = f"📊 {MONTHS_RU[today.month].upper()} {today.year} — ПОЛНЫЙ ОТЧЁТ\n\n"
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
                text += f"            💰 День: {int(day_total)} руб\n"
            if current_category is not None:
                text += f"      📊 Категория: {int(cat_total)} руб\n"
            if current_worker is not None:
                text += f"   ━━━━━━━━━━━━━━\n"
                text += f"   📊 Дней: {len(worker_days)} | 💰 Итого: {int(worker_total)} руб\n\n"
                grand_total += worker_total
            current_worker = wname
            current_category = None
            current_date = None
            worker_total = 0
            cat_total = 0
            day_total = 0
            worker_days = set()
            cats = await get_worker_categories(tid)
            ce = "".join([c[2] for c in cats]) if cats else ""
            text += f"👤 {wname} {ce}\n"

        if cname != current_category:
            if current_date is not None:
                text += f"            💰 День: {int(day_total)} руб\n"
                day_total = 0
            if current_category is not None:
                text += f"      📊 Категория: {int(cat_total)} руб\n\n"
            current_category = cname
            current_date = None
            cat_total = 0
            text += f"   {cemoji} {cname}:\n"

        if wdate != current_date:
            if current_date is not None:
                text += f"            💰 День: {int(day_total)} руб\n"
            text += f"      📅 {format_date_short(wdate)}:\n"
            current_date = wdate
            day_total = 0
            worker_days.add(wdate)

        text += f"         ▫️ {pname}: {int(qty)} x {int(price)} = {int(total)} руб\n"
        worker_total += total
        cat_total += total
        day_total += total

    if current_date is not None:
        text += f"            💰 День: {int(day_total)} руб\n"
    if current_category is not None:
        text += f"      📊 Категория: {int(cat_total)} руб\n"
    if current_worker is not None:
        text += f"   ━━━━━━━━━━━━━━\n"
        text += f"   📊 Дней: {len(worker_days)} | 💰 Итого: {int(worker_total)} руб\n\n"
        grand_total += worker_total

    text += f"━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 ОБЩИЙ ФОНД: {int(grand_total)} руб"
    await send_long_message(message, text)


# ==================== ЗАПИСИ РАБОТНИКОВ ====================

@dp.message(F.text == "🔧 Записи работников", AdminFilter())
async def admin_entries_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = [[InlineKeyboardButton(text=f"👤 {n}", callback_data=f"ae_w:{t}")] for t, n in workers]
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminManageEntries.choosing_worker)

@dp.callback_query(F.data.startswith("ae_w:"), AdminManageEntries.choosing_worker)
async def admin_entries_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    wname = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=wname)
    entries = await get_worker_recent_entries(wid, limit=20)
    if not entries:
        await callback.message.edit_text(f"📭 У {wname} нет записей.")
        await state.clear()
        await callback.answer()
        return
    text = f"📋 {wname}:\n\n"
    buttons = []
    current_date = ""
    for eid, name, qty, price, total, wdate, created in entries:
        if wdate != current_date:
            text += f"\n📅 {format_date(wdate)}:\n"
            current_date = wdate
        text += f"   🔹 {name} x {int(qty)} = {int(total)} руб\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {name}x{int(qty)}={int(total)}руб ({wdate})",
            callback_data=f"ae_e:{eid}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ae_back")])
    await callback.message.edit_text(text + "\n\nВыберите запись:",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminManageEntries.viewing_entries)
    await callback.answer()

@dp.callback_query(F.data.startswith("ae_e:"), AdminManageEntries.viewing_entries)
async def admin_entry_chosen(callback: types.CallbackQuery, state: FSMContext):
    eid = int(callback.data.split(":")[1])
    entry = await get_entry_by_id(eid)
    if not entry:
        await callback.answer("Не найдена", show_alert=True)
        return
    await state.update_data(entry_id=eid)
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить кол-во", callback_data="ae_act:edit")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="ae_act:delete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="ae_act:back")]
    ]
    await callback.message.edit_text(
        f"📦 {entry[1]}\n\n"
        f"👤 {entry[7]}\n"
        f"📅 {format_date(entry[5])}\n"
        f"🔢 Кол-во: {int(entry[2])} шт\n"
        f"💵 Расценка: {int(entry[3])} руб\n"
        f"💰 Сумма: {int(entry[4])} руб",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminManageEntries.choosing_action)
    await callback.answer()

@dp.callback_query(F.data.startswith("ae_act:"), AdminManageEntries.choosing_action)
async def admin_entry_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    if action == "edit":
        await callback.message.edit_text("Введите правильное количество:")
        await state.set_state(AdminManageEntries.entering_new_quantity)
        await callback.answer()
    elif action == "delete":
        data = await state.get_data()
        entry = await get_entry_by_id(data["entry_id"])
        buttons = [
            [InlineKeyboardButton(text="✅ Да!", callback_data="ae_del:yes")],
            [InlineKeyboardButton(text="❌ Нет", callback_data="ae_del:no")]
        ]
        await callback.message.edit_text(
            f"⚠️ Удалить?\n📦 {entry[1]} x {int(entry[2])} = {int(entry[4])} руб",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(AdminManageEntries.confirming_delete)
        await callback.answer()
    elif action == "back":
        data = await state.get_data()
        entries = await get_worker_recent_entries(data["worker_id"], limit=20)
        text = f"📋 {data['worker_name']}:\n\n"
        buttons = []
        current_date = ""
        for eid, name, qty, price, total, wdate, created in entries:
            if wdate != current_date:
                text += f"\n📅 {format_date(wdate)}:\n"
                current_date = wdate
            text += f"   🔹 {name} x {int(qty)} = {int(total)} руб\n"
            buttons.append([InlineKeyboardButton(
                text=f"📦 {name}x{int(qty)}={int(total)}руб",
                callback_data=f"ae_e:{eid}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="ae_back")])
        await callback.message.edit_text(text + "\n\nВыберите:",
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
    entry = await get_entry_by_id(data["entry_id"])
    if not entry:
        await message.answer("❌ Не найдена.")
        await state.clear()
        return
    old_qty = entry[2]
    old_total = entry[4]
    new_total = new_qty * entry[3]
    await update_entry_quantity(data["entry_id"], new_qty)
    await message.answer(
        f"✅ Изменено!\n\n📦 {entry[1]} ({entry[7]})\n"
        f"Было: {int(old_qty)}шт = {int(old_total)} руб\n"
        f"Стало: {new_qty}шт = {int(new_total)} руб",
        reply_markup=get_edit_keyboard()
    )
    await state.clear()

@dp.callback_query(F.data.startswith("ae_del:"), AdminManageEntries.confirming_delete)
async def admin_entry_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        deleted = await delete_entry_by_id(data["entry_id"])
        if deleted:
            await callback.message.edit_text(
                f"✅ Удалено: {deleted[1]} x {int(deleted[2])} = {int(deleted[3])} руб")
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

@dp.message(F.text == "💳 Выдать аванс", StaffFilter())
async def advance_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    today = date.today()
    buttons = []
    for tid, name in workers:
        adv_total = await get_worker_advances_total(tid, today.year, today.month)
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name} (аванс: {int(adv_total)} руб)",
            callback_data=f"adv_w:{tid}"
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("👤 Кому выдать аванс?",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminAdvance.choosing_worker)

@dp.callback_query(F.data.startswith("adv_w:"), AdminAdvance.choosing_worker)
async def advance_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    wname = next((n for t, n in workers if t == wid), "?")
    today = date.today()
    stats = await get_worker_full_stats(wid, today.year, today.month)
    await state.update_data(worker_id=wid, worker_name=wname)
    await callback.message.edit_text(
        f"👤 {wname}\n\n"
        f"💰 Заработано: {int(stats['earned'])} руб\n"
        f"💳 Авансы: {int(stats['advances'])} руб\n"
        f"⚠️ Штрафы: {int(stats['penalties'])} руб\n"
        f"📊 Остаток: {int(stats['balance'])} руб\n\n"
        f"Введите сумму аванса:"
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
    await message.answer(f"💳 Сумма: {int(amount)} руб\n\nВведите комментарий (или - чтобы пропустить):")
    await state.set_state(AdminAdvance.entering_comment)

@dp.message(AdminAdvance.entering_comment)
async def advance_comment(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    if comment == "-":
        comment = ""
    data = await state.get_data()
    await add_advance(data["worker_id"], data["amount"], comment)
    today = date.today()
    stats = await get_worker_full_stats(data["worker_id"], today.year, today.month)
    text = (
        f"✅ Аванс выдан!\n\n"
        f"👤 {data['worker_name']}\n"
        f"💳 Сумма: {int(data['amount'])} руб\n"
    )
    if comment:
        text += f"💬 {comment}\n"
    text += (
        f"\n📊 Баланс:\n"
        f"💰 Заработано: {int(stats['earned'])} руб\n"
        f"💳 Авансы: {int(stats['advances'])} руб\n"
        f"⚠️ Штрафы: {int(stats['penalties'])} руб\n"
        f"📊 Остаток: {int(stats['balance'])} руб"
    )
    await message.answer(text, reply_markup=get_money_keyboard())

    # Уведомление работнику
    try:
        notify = f"💳 Вам выдан аванс: {int(data['amount'])} руб"
        if comment:
            notify += f"\n💬 {comment}"
        notify += f"\n📊 Остаток к выплате: {int(stats['balance'])} руб"
        await bot.send_message(data["worker_id"], notify)
    except Exception as e:
        logging.error(f"Notify worker advance: {e}")

    # Уведомление админу если менеджер
    if message.from_user.id != ADMIN_ID:
        try:
            admin_notify = (
                f"📬 Менеджер выдал аванс!\n\n"
                f"👤 Менеджер: {message.from_user.full_name}\n"
                f"👤 Работник: {data['worker_name']}\n"
                f"💳 Сумма: {int(data['amount'])} руб"
            )
            if comment:
                admin_notify += f"\n💬 {comment}"
            await bot.send_message(ADMIN_ID, admin_notify)
        except Exception as e:
            logging.error(f"Notify admin about advance: {e}")

    await state.clear()

@dp.message(F.text == "💳 Удалить аванс", StaffFilter())
async def delete_advance_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    buttons = []
    today = date.today()
    for tid, name in workers:
        advances = await get_worker_advances(tid, today.year, today.month)
        if advances:
            total = sum(a[1] for a in advances)
            buttons.append([InlineKeyboardButton(
                text=f"👤 {name} ({int(total)} руб, {len(advances)} шт)",
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
    workers = await get_all_workers()
    wname = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=wname)
    today = date.today()
    advances = await get_worker_advances(wid, today.year, today.month)
    buttons = []
    for adv_id, amount, comment, adv_date, created in advances:
        label = f"{format_date_short(adv_date)} — {int(amount)} руб"
        if comment:
            label += f" ({comment[:20]})"
        buttons.append([InlineKeyboardButton(text=f"💳 {label}", callback_data=f"dadv_a:{adv_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="cdel")])
    await callback.message.edit_text(
        f"👤 {wname} — авансы:\n\nВыберите для удаления:",
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
    await callback.message.edit_text("⚠️ Удалить этот аванс?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeleteAdvance.confirming)
    await callback.answer()

@dp.callback_query(F.data.startswith("dadv_c:"), AdminDeleteAdvance.confirming)
async def del_advance_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        deleted = await delete_advance(data["advance_id"])
        if deleted:
            await callback.message.edit_text(f"✅ Аванс {int(deleted[1])} руб удалён!")
        else:
            await callback.message.edit_text("❌ Не найден.")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


# ==================== ШТРАФЫ ====================

@dp.message(F.text == "⚠️ Выписать штраф", StaffFilter())
async def penalty_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    today = date.today()
    buttons = []
    for tid, name in workers:
        pen_total = await get_worker_penalties_total(tid, today.year, today.month)
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name} (штрафы: {int(pen_total)} руб)",
            callback_data=f"pen_w:{tid}"
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("👤 Кому выписать штраф?",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminPenalty.choosing_worker)

@dp.callback_query(F.data.startswith("pen_w:"), AdminPenalty.choosing_worker)
async def penalty_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    wname = next((n for t, n in workers if t == wid), "?")
    today = date.today()
    stats = await get_worker_full_stats(wid, today.year, today.month)
    await state.update_data(worker_id=wid, worker_name=wname)
    await callback.message.edit_text(
        f"👤 {wname}\n\n"
        f"💰 Заработано: {int(stats['earned'])} руб\n"
        f"💳 Авансы: {int(stats['advances'])} руб\n"
        f"⚠️ Штрафы: {int(stats['penalties'])} руб\n"
        f"📊 Остаток: {int(stats['balance'])} руб\n\n"
        f"Введите сумму штрафа:"
    )
    await state.set_state(AdminPenalty.entering_amount)
    await callback.answer()

@dp.message(AdminPenalty.entering_amount)
async def penalty_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число!")
        return
    await state.update_data(amount=amount)
    await message.answer(f"⚠️ Сумма: {int(amount)} руб\n\nВведите причину штрафа (или - чтобы пропустить):")
    await state.set_state(AdminPenalty.entering_reason)

@dp.message(AdminPenalty.entering_reason)
async def penalty_reason(message: types.Message, state: FSMContext):
    reason = message.text.strip()
    if reason == "-":
        reason = ""
    data = await state.get_data()
    await add_penalty(data["worker_id"], data["amount"], reason)
    today = date.today()
    stats = await get_worker_full_stats(data["worker_id"], today.year, today.month)
    text = (
        f"✅ Штраф выписан!\n\n"
        f"👤 {data['worker_name']}\n"
        f"⚠️ Сумма: {int(data['amount'])} руб\n"
    )
    if reason:
        text += f"📝 Причина: {reason}\n"
    text += (
        f"\n📊 Баланс:\n"
        f"💰 Заработано: {int(stats['earned'])} руб\n"
        f"💳 Авансы: {int(stats['advances'])} руб\n"
        f"⚠️ Штрафы: {int(stats['penalties'])} руб\n"
        f"📊 Остаток: {int(stats['balance'])} руб"
    )
    await message.answer(text, reply_markup=get_money_keyboard())

    # Уведомление работнику
    try:
        notify = f"⚠️ Вам выписан штраф: {int(data['amount'])} руб"
        if reason:
            notify += f"\n📝 Причина: {reason}"
        notify += f"\n📊 Остаток к выплате: {int(stats['balance'])} руб"
        await bot.send_message(data["worker_id"], notify)
    except Exception as e:
        logging.error(f"Notify worker penalty: {e}")

    # Уведомление админу если менеджер
    if message.from_user.id != ADMIN_ID:
        try:
            admin_notify = (
                f"📬 Менеджер выписал штраф!\n\n"
                f"👤 Менеджер: {message.from_user.full_name}\n"
                f"👤 Работник: {data['worker_name']}\n"
                f"⚠️ Сумма: {int(data['amount'])} руб"
            )
            if reason:
                admin_notify += f"\n📝 Причина: {reason}"
            await bot.send_message(ADMIN_ID, admin_notify)
        except Exception as e:
            logging.error(f"Notify admin about penalty: {e}")

    await state.clear()

@dp.message(F.text == "⚠️ Удалить штраф", StaffFilter())
async def delete_penalty_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    buttons = []
    today = date.today()
    for tid, name in workers:
        penalties = await get_worker_penalties(tid, today.year, today.month)
        if penalties:
            total = sum(p[1] for p in penalties)
            buttons.append([InlineKeyboardButton(
                text=f"👤 {name} ({int(total)} руб, {len(penalties)} шт)",
                callback_data=f"dpen_w:{tid}"
            )])
    if not buttons:
        await message.answer("📭 Нет штрафов за этот месяц.")
        return
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cdel")])
    await message.answer("👤 Выберите работника:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeletePenalty.choosing_worker)

@dp.callback_query(F.data.startswith("dpen_w:"), AdminDeletePenalty.choosing_worker)
async def del_penalty_worker(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    wname = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=wname)
    today = date.today()
    penalties = await get_worker_penalties(wid, today.year, today.month)
    buttons = []
    for pen_id, amount, reason, pen_date, created in penalties:
        label = f"{format_date_short(pen_date)} — {int(amount)} руб"
        if reason:
            label += f" ({reason[:20]})"
        buttons.append([InlineKeyboardButton(text=f"⚠️ {label}", callback_data=f"dpen_p:{pen_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="cdel")])
    await callback.message.edit_text(
        f"👤 {wname} — штрафы:\n\nВыберите для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminDeletePenalty.choosing_penalty)
    await callback.answer()

@dp.callback_query(F.data.startswith("dpen_p:"), AdminDeletePenalty.choosing_penalty)
async def del_penalty_chosen(callback: types.CallbackQuery, state: FSMContext):
    pen_id = int(callback.data.split(":")[1])
    await state.update_data(penalty_id=pen_id)
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить!", callback_data="dpen_c:yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="dpen_c:no")]
    ]
    await callback.message.edit_text("⚠️ Удалить этот штраф?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminDeletePenalty.confirming)
    await callback.answer()

@dp.callback_query(F.data.startswith("dpen_c:"), AdminDeletePenalty.confirming)
async def del_penalty_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        deleted = await delete_penalty(data["penalty_id"])
        if deleted:
            await callback.message.edit_text(f"✅ Штраф {int(deleted[1])} руб удалён!")
        else:
            await callback.message.edit_text("❌ Не найден.")
    else:
        await callback.message.edit_text("❌ Отменено.")
    await state.clear()
    await callback.answer()


# ==================== БАЛАНС ====================

@dp.message(F.text == "💰 Баланс работников", StaffFilter())
async def show_balances(message: types.Message, state: FSMContext):
    await state.clear()
    today = date.today()
    balances = await get_all_workers_balance(today.year, today.month)

    text = f"💰 Баланс — {MONTHS_RU[today.month]} {today.year}\n\n"
    grand_earned = 0
    grand_advance = 0
    grand_penalty = 0
    for tid, name, earned, advances, penalties, work_days in balances:
        balance = earned - advances - penalties
        if earned > 0 or advances > 0 or penalties > 0:
            icon = "✅" if balance >= 0 else "⚠️"
            text += f"{icon} {name}\n"
            text += f"   💰 Заработано: {int(earned)} руб\n"
            text += f"   💳 Авансы: {int(advances)} руб\n"
            if penalties > 0:
                text += f"   ⚠️ Штрафы: {int(penalties)} руб\n"
            text += f"   📊 Остаток: {int(balance)} руб\n\n"
            grand_earned += earned
            grand_advance += advances
            grand_penalty += penalties
    text += f"━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 Всего заработано: {int(grand_earned)} руб\n"
    text += f"💳 Всего авансов: {int(grand_advance)} руб\n"
    if grand_penalty > 0:
        text += f"⚠️ Всего штрафов: {int(grand_penalty)} руб\n"
    text += f"📊 Общий остаток: {int(grand_earned - grand_advance - grand_penalty)} руб"
    await send_long_message(message, text)


# ==================== ЗАРАБОТОК ЗА МЕСЯЦ ====================

@dp.message(F.text == "📊 Заработок за месяц", StaffFilter())
async def earnings_month(message: types.Message, state: FSMContext):
    await state.clear()
    today = date.today()
    workers = await get_all_workers()

    text = f"📊 Заработок — {MONTHS_RU[today.month]} {today.year}\n\n"
    grand_total = 0

    for tid, name in workers:
        monthly = await get_monthly_total(tid, today.year, today.month)
        earned = sum(r[3] for r in monthly)
        cats = await get_worker_categories(tid)
        ce = "".join([c[2] for c in cats]) if cats else ""

        if earned > 0:
            details = await get_worker_monthly_details(tid, today.year, today.month)
            text += f"👤 {name} {ce}\n"
            current_cat = ""
            for pl_name, c_emoji, c_name, qty, price, total in details:
                if c_name != current_cat:
                    current_cat = c_name
                    text += f"   {c_emoji} {c_name}:\n"
                text += f"      ▫️ {pl_name}: {int(qty)}шт x {int(price)} руб = {int(total)} руб\n"
            text += f"   💰 Итого: {int(earned)} руб\n\n"
        else:
            text += f"❌ {name} {ce} — нет записей\n\n"
        grand_total += earned

    text += f"━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 ОБЩИЙ ФОНД: {int(grand_total)} руб"
    await send_long_message(message, text)


# ==================== РЕЙТИНГ ====================

@dp.message(F.text == "🏆 Рейтинг работников", StaffFilter())
async def workers_rating(message: types.Message, state: FSMContext):
    await state.clear()
    today = date.today()
    balances = await get_all_workers_balance(today.year, today.month)

    worker_stats = []
    no_records = []

    for tid, name, earned, advances, penalties, work_days in balances:
        if earned > 0:
            avg_per_day = earned / work_days if work_days > 0 else 0
            worker_stats.append((tid, name, earned, work_days, avg_per_day, advances, penalties))
        else:
            no_records.append((tid, name))

    if not worker_stats and not no_records:
        await message.answer("📭 Нет данных за этот месяц.")
        return

    medals = ["🥇", "🥈", "🥉"]
    text = f"🏆 Рейтинг — {MONTHS_RU[today.month]} {today.year}\n\n"

    if worker_stats:
        worker_stats.sort(key=lambda x: x[2], reverse=True)
        text += f"📊 По заработку:\n\n"
        for i, (tid, name, earned, days, avg, adv, pen) in enumerate(worker_stats):
            medal = medals[i] if i < 3 else f"  {i+1}."
            balance = earned - adv - pen
            text += (
                f"{medal} {name}\n"
                f"   💰 Заработок: {int(earned)} руб\n"
                f"   📅 Дней: {days}\n"
                f"   📊 Среднее/день: {int(avg)} руб\n"
                f"   💳 Авансы: {int(adv)} руб\n"
            )
            if pen > 0:
                text += f"   ⚠️ Штрафы: {int(pen)} руб\n"
            text += f"   📊 Остаток: {int(balance)} руб\n\n"

        worker_stats.sort(key=lambda x: x[4], reverse=True)
        text += f"\n📊 По среднему за день:\n\n"
        for i, (tid, name, earned, days, avg, adv, pen) in enumerate(worker_stats):
            medal = medals[i] if i < 3 else f"  {i+1}."
            text += f"{medal} {name} — {int(avg)} руб/день ({days} дн.)\n"

    if no_records:
        text += f"\n\n❌ Без записей:\n"
        for tid, name in no_records:
            text += f"   ▫️ {name}\n"

    await send_long_message(message, text)


# ==================== ИТОГИ МЕСЯЦА ====================

@dp.message(F.text == "💼 Итоги месяца", StaffFilter())
async def month_salary_summary(message: types.Message, state: FSMContext):
    await state.clear()
    today = date.today()
    balances = await get_all_workers_balance(today.year, today.month)

    text = f"💼 ИТОГИ МЕСЯЦА — {MONTHS_RU[today.month]} {today.year}\n"
    text += f"━━━━━━━━━━━━━━━━━━━\n\n"

    grand_earned = 0
    grand_advance = 0
    grand_penalty = 0
    grand_to_pay = 0
    worker_list = []

    for tid, name, earned, advances, penalties, work_days in balances:
        to_pay = earned - advances - penalties
        if earned > 0 or advances > 0 or penalties > 0:
            worker_list.append({
                'name': name, 'earned': earned,
                'advance': advances, 'penalty': penalties,
                'to_pay': to_pay, 'days': work_days
            })
            grand_earned += earned
            grand_advance += advances
            grand_penalty += penalties
            grand_to_pay += to_pay

    if not worker_list:
        await message.answer("📭 Нет данных за этот месяц.")
        return

    worker_list.sort(key=lambda x: x['earned'], reverse=True)

    for w in worker_list:
        if w['to_pay'] > 0:
            icon = "💰"
        elif w['to_pay'] == 0:
            icon = "✅"
        else:
            icon = "⚠️"
        text += f"{icon} {w['name']}\n"
        text += f"   📅 Рабочих дней: {w['days']}\n"
        text += f"   💰 Заработано: {int(w['earned'])} руб\n"
        text += f"   💳 Авансы: {int(w['advance'])} руб\n"
        if w['penalty'] > 0:
            text += f"   ⚠️ Штрафы: {int(w['penalty'])} руб\n"
        text += f"   📊 К выплате: {int(w['to_pay'])} руб\n\n"

    text += f"━━━━━━━━━━━━━━━━━━━\n"
    text += f"👥 Работников: {len(worker_list)}\n"
    text += f"💰 Общий фонд зарплат: {int(grand_earned)} руб\n"
    text += f"💳 Выдано авансами: {int(grand_advance)} руб\n"
    if grand_penalty > 0:
        text += f"⚠️ Штрафы: {int(grand_penalty)} руб\n"
    text += f"💼 Осталось выплатить: {int(grand_to_pay)} руб\n"
    text += f"━━━━━━━━━━━━━━━━━━━\n\n"

    if grand_to_pay > 0:
        text += f"💡 Нужно подготовить {int(grand_to_pay)} руб для выдачи зарплат"
    elif grand_to_pay == 0:
        text += f"✅ Все зарплаты выплачены!"
    else:
        text += f"⚠️ Переплата на {int(abs(grand_to_pay))} руб"

    await send_long_message(message, text)


# ==================== EXCEL ОТЧЁТЫ ====================

@dp.message(F.text == "📥 Отчёт месяц", StaffFilter())
async def report_month(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⏳ Формирую...")
    try:
        today = date.today()
        fn = await generate_monthly_report(today.year, today.month)
        await message.answer_document(FSInputFile(fn), caption="📊 Отчёт за месяц")
        os.remove(fn)
    except Exception as e:
        logging.exception(f"Report error: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(F.text == "📥 Отчёт работник", StaffFilter())
async def report_worker_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("⚠️ Нет работников.")
        return
    buttons = [[InlineKeyboardButton(text=f"👤 {n}", callback_data=f"rw:{t}")] for t, n in workers]
    await message.answer("Работник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(ReportWorker.choosing_worker)

@dp.callback_query(F.data.startswith("rw:"), ReportWorker.choosing_worker)
async def report_worker_gen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    name = next((n for t, n in workers if t == wid), "Работник")
    await callback.message.edit_text("⏳ Формирую...")
    try:
        today = date.today()
        fn = await generate_worker_report(wid, name, today.year, today.month)
        await callback.message.answer_document(FSInputFile(fn), caption=f"📊 {name}")
        os.remove(fn)
    except Exception as e:
        logging.exception(f"Report error: {e}")
        await callback.message.answer(f"❌ Ошибка: {e}")
    await state.clear()
    await callback.answer()


# ==================== НАСТРОЙКА НАПОМИНАНИЙ ====================

@dp.message(F.text == "⏰ Напоминания", AdminFilter())
async def reminder_settings_menu(message: types.Message, state: FSMContext):
    await state.clear()
    settings = await get_reminder_settings()

    ev_status = "✅" if settings['evening_enabled'] else "❌"
    lt_status = "✅" if settings['late_enabled'] else "❌"
    rp_status = "✅" if settings['report_enabled'] else "❌"

    text = (
        "⏰ Настройка напоминаний\n\n"
        f"{ev_status} Вечернее: {settings['evening_hour']:02d}:{settings['evening_minute']:02d}\n"
        f"{lt_status} Позднее: {settings['late_hour']:02d}:{settings['late_minute']:02d}\n"
        f"{rp_status} Отчёт админу: {settings['report_hour']:02d}:{settings['report_minute']:02d}\n"
        f"\nОбновлено: {datetime.now().strftime('%H:%M:%S')}"
    )

    buttons = [
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['evening_enabled'] else '🟢'} Вечернее {'выкл' if settings['evening_enabled'] else 'вкл'}",
            callback_data="rem:toggle_evening"
        )],
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['late_enabled'] else '🟢'} Позднее {'выкл' if settings['late_enabled'] else 'вкл'}",
            callback_data="rem:toggle_late"
        )],
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['report_enabled'] else '🟢'} Отчёт {'выкл' if settings['report_enabled'] else 'вкл'}",
            callback_data="rem:toggle_report"
        )],
        [InlineKeyboardButton(text="🕐 Время вечернего", callback_data="rem:time_evening")],
        [InlineKeyboardButton(text="🕐 Время позднего", callback_data="rem:time_late")],
        [InlineKeyboardButton(text="🕐 Время отчёта", callback_data="rem:time_report")],
        [InlineKeyboardButton(text="🔄 Применить", callback_data="rem:apply")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="rem:back")],
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminReminderSettings.main_menu)


@dp.callback_query(F.data.startswith("rem:"), AdminReminderSettings.main_menu)
async def reminder_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    settings = await get_reminder_settings()

    if action == "toggle_evening":
        new_val = not settings['evening_enabled']
        await update_reminder_settings(evening_enabled=int(new_val))
        await callback.answer(f"Вечернее: {'ВКЛ' if new_val else 'ВЫКЛ'}")
    elif action == "toggle_late":
        new_val = not settings['late_enabled']
        await update_reminder_settings(late_enabled=int(new_val))
        await callback.answer(f"Позднее: {'ВКЛ' if new_val else 'ВЫКЛ'}")
    elif action == "toggle_report":
        new_val = not settings['report_enabled']
        await update_reminder_settings(report_enabled=int(new_val))
        await callback.answer(f"Отчёт: {'ВКЛ' if new_val else 'ВЫКЛ'}")
    elif action in ("time_evening", "time_late", "time_report"):
        await state.update_data(time_target=action.replace("time_", ""))
        await callback.message.edit_text("Введите время в формате ЧЧ:ММ\n\nНапример: 18:30")
        await state.set_state(AdminReminderSettings.entering_time)
        await callback.answer()
        return
    elif action == "apply":
        await reschedule_reminders()
        await callback.answer("✅ Расписание обновлено!", show_alert=True)
    elif action == "back":
        await state.clear()
        await callback.message.edit_text("👌 Ок")
        await callback.answer()
        return

    settings = await get_reminder_settings()
    ev_status = "✅" if settings['evening_enabled'] else "❌"
    lt_status = "✅" if settings['late_enabled'] else "❌"
    rp_status = "✅" if settings['report_enabled'] else "❌"

    text = (
        f"⏰ Настройка напоминаний\n\n"
        f"{ev_status} Вечернее: {settings['evening_hour']:02d}:{settings['evening_minute']:02d}\n"
        f"{lt_status} Позднее: {settings['late_hour']:02d}:{settings['late_minute']:02d}\n"
        f"{rp_status} Отчёт админу: {settings['report_hour']:02d}:{settings['report_minute']:02d}\n"
        f"\nОбновлено: {datetime.now().strftime('%H:%M:%S')}"
    )

    buttons = [
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['evening_enabled'] else '🟢'} Вечернее {'выкл' if settings['evening_enabled'] else 'вкл'}",
            callback_data="rem:toggle_evening"
        )],
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['late_enabled'] else '🟢'} Позднее {'выкл' if settings['late_enabled'] else 'вкл'}",
            callback_data="rem:toggle_late"
        )],
        [InlineKeyboardButton(
            text=f"{'🔴' if settings['report_enabled'] else '🟢'} Отчёт {'выкл' if settings['report_enabled'] else 'вкл'}",
            callback_data="rem:toggle_report"
        )],
        [InlineKeyboardButton(text="🕐 Время вечернего", callback_data="rem:time_evening")],
        [InlineKeyboardButton(text="🕐 Время позднего", callback_data="rem:time_late")],
        [InlineKeyboardButton(text="🕐 Время отчёта", callback_data="rem:time_report")],
        [InlineKeyboardButton(text="🔄 Применить", callback_data="rem:apply")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="rem:back")],
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        pass


@dp.message(AdminReminderSettings.entering_time)
async def reminder_time_entered(message: types.Message, state: FSMContext):
    try:
        parts = message.text.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("❌ Формат: ЧЧ:ММ (например 18:30)")
        return

    data = await state.get_data()
    target = data["time_target"]

    if target == "evening":
        await update_reminder_settings(evening_hour=hour, evening_minute=minute)
    elif target == "late":
        await update_reminder_settings(late_hour=hour, late_minute=minute)
    elif target == "report":
        await update_reminder_settings(report_hour=hour, report_minute=minute)

    await message.answer(
        f"✅ Время установлено: {hour:02d}:{minute:02d}\n\n"
        f"Нажмите 🔄 Применить чтобы обновить расписание.",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()


async def reschedule_reminders():
    settings = await get_reminder_settings()
    for job_id in ['evening_reminder', 'late_reminder', 'admin_report', 'auto_backup']:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
    if settings['evening_enabled']:
        scheduler.add_job(safe_evening_reminder, "cron",
            hour=settings['evening_hour'], minute=settings['evening_minute'],
            id='evening_reminder', replace_existing=True)
    if settings['late_enabled']:
        scheduler.add_job(safe_late_reminder, "cron",
            hour=settings['late_hour'], minute=settings['late_minute'],
            id='late_reminder', replace_existing=True)
    if settings['report_enabled']:
        scheduler.add_job(safe_admin_report, "cron",
            hour=settings['report_hour'], minute=settings['report_minute'],
            id='admin_report', replace_existing=True)
    scheduler.add_job(safe_backup, "cron", hour=23, minute=0,
        id='auto_backup', replace_existing=True)


# ==================== БЭКАП ====================

@dp.message(F.text == "💾 Бэкап БД", AdminFilter())
async def manual_backup(message: types.Message, state: FSMContext):
    await state.clear()
    await send_backup(message.from_user.id)

async def send_backup(chat_id=None):
    if chat_id is None:
        chat_id = ADMIN_ID
    possible_paths = [
        DB_NAME,
        os.path.join(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "."), "production.db"),
        "production.db",
        os.path.abspath(DB_NAME),
    ]
    db_path = None
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            break
    if db_path is None:
        try:
            cwd = os.getcwd()
            files = os.listdir(cwd)
            vol_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "не задан")
            vol_files = []
            if os.path.exists(vol_path):
                vol_files = os.listdir(vol_path)
            debug_text = (
                f"❌ База данных не найдена!\n\n"
                f"Рабочая папка: {cwd}\nФайлы: {files}\n\n"
                f"Volume: {vol_path}\nФайлы: {vol_files}\n\nDB_NAME: {DB_NAME}"
            )
            await bot.send_message(chat_id, debug_text)
        except Exception as e:
            await bot.send_message(chat_id, f"❌ База не найдена. Ошибка: {e}")
        return
    try:
        now = datetime.now()
        caption = f"💾 Бэкап БД\n📅 {now.strftime('%d.%m.%Y %H:%M')}\n📁 {db_path}"
        await bot.send_document(chat_id,
            FSInputFile(db_path, filename=f"backup_{now.strftime('%Y%m%d_%H%M')}.db"),
            caption=caption)
    except Exception as e:
        logging.error(f"Backup error: {e}")
        try:
            await bot.send_message(chat_id, f"❌ Ошибка бэкапа: {e}")
        except Exception:
            pass


# ==================== НАПОМИНАНИЯ ====================

async def send_evening_reminder():
    settings = await get_reminder_settings()
    if not settings['evening_enabled']:
        return
    for tid, name in await get_workers_without_records():
        try:
            await bot.send_message(tid, "🔔 Запишите работу за сегодня!")
        except Exception as e:
            logging.error(f"Reminder {name}: {e}")

async def send_late_reminder():
    settings = await get_reminder_settings()
    if not settings['late_enabled']:
        return
    for tid, name in await get_workers_without_records():
        try:
            await bot.send_message(tid, "⚠️ Вы не записали работу! Нужно для зарплаты.")
        except Exception as e:
            logging.error(f"Late {name}: {e}")

async def send_admin_report():
    settings = await get_reminder_settings()
    if not settings['report_enabled']:
        return
    summary = await get_all_workers_daily_summary()
    text = f"📊 Итоги {date.today().strftime('%d.%m.%Y')}:\n\n"
    total = 0
    for tid, name, dt in summary:
        icon = '✅' if dt > 0 else '❌'
        text += f"{icon} {name}: {int(dt)} руб\n"
        total += dt
    text += f"\n💰 Итого: {int(total)} руб"
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logging.error(f"Admin report: {e}")

async def safe_evening_reminder():
    try:
        await send_evening_reminder()
    except Exception as e:
        logging.exception(f"Evening reminder failed: {e}")
        try:
            await bot.send_message(ADMIN_ID, f"🚨 Ошибка вечернего напоминания: {e}")
        except Exception:
            pass

async def safe_late_reminder():
    try:
        await send_late_reminder()
    except Exception as e:
        logging.exception(f"Late reminder failed: {e}")
        try:
            await bot.send_message(ADMIN_ID, f"🚨 Ошибка позднего напоминания: {e}")
        except Exception:
            pass

async def safe_admin_report():
    try:
        await send_admin_report()
    except Exception as e:
        logging.exception(f"Admin report failed: {e}")
        try:
            await bot.send_message(ADMIN_ID, f"🚨 Ошибка отчёта: {e}")
        except Exception:
            pass

async def safe_backup():
    try:
        await send_backup(ADMIN_ID)
    except Exception as e:
        logging.exception(f"Backup failed: {e}")
        try:
            await bot.send_message(ADMIN_ID, f"🚨 Ошибка бэкапа: {e}")
        except Exception:
            pass


# ==================== ЗАПУСК ====================

async def main():
    await init_db()
    settings = await get_reminder_settings()
    if settings['evening_enabled']:
        scheduler.add_job(safe_evening_reminder, "cron",
            hour=settings['evening_hour'], minute=settings['evening_minute'],
            id='evening_reminder')
    if settings['late_enabled']:
        scheduler.add_job(safe_late_reminder, "cron",
            hour=settings['late_hour'], minute=settings['late_minute'],
            id='late_reminder')
    if settings['report_enabled']:
        scheduler.add_job(safe_admin_report, "cron",
            hour=settings['report_hour'], minute=settings['report_minute'],
            id='admin_report')
    scheduler.add_job(safe_backup, "cron", hour=23, minute=0, id='auto_backup')
    scheduler.start()
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())