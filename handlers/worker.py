from datetime import date, timedelta
import logging

from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID, MANAGER_IDS, BOT_TOKEN
from database import (
    get_price_list_for_worker, get_worker_categories,
    add_work, get_daily_total, get_monthly_total,
    get_monthly_by_days, get_price_list,
    get_worker_entries_by_custom_date, get_entry_by_id,
    delete_entry_by_id,
    get_worker_full_stats, get_worker_advances, get_worker_penalties
)
from states import WorkEntry, ViewEntries, WorkerDeleteEntry
from keyboards import make_date_picker, make_work_buttons
from utils import format_date, format_date_short, parse_user_date, send_long_message, MONTHS_RU
from keyboards import get_main_keyboard

router = Router()
bot = Bot(token=BOT_TOKEN)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def to_date_str(value) -> str:
    """Всегда возвращает строку формата YYYY-MM-DD"""
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value[:10]
    return date.today().isoformat()


def is_today(date_value) -> bool:
    """Проверяет является ли дата сегодняшней"""
    return to_date_str(date_value) == date.today().isoformat()


# ==================== ЗАПИСАТЬ РАБОТУ ====================

@router.message(F.text == "📝 Записать работу")
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


@router.callback_query(F.data.startswith("wdate:"), WorkEntry.choosing_date)
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


@router.message(WorkEntry.entering_custom_date)
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


@router.callback_query(F.data == "wdate_back")
async def work_back_to_dates(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📅 За какой день записать работу?",
        reply_markup=make_date_picker("wdate", "cancel")
    )
    await state.set_state(WorkEntry.choosing_date)
    await callback.answer()


@router.callback_query(F.data.startswith("wcat:"), WorkEntry.choosing_category)
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


@router.callback_query(F.data == "wcat_back", WorkEntry.choosing_work)
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


@router.callback_query(F.data.startswith("work:"), WorkEntry.choosing_work)
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


@router.message(WorkEntry.entering_quantity)
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


@router.callback_query(F.data.startswith("confirm_large:"), WorkEntry.confirming_large)
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
    work_date = to_date_str(data.get("work_date", date.today().isoformat()))

    total = await add_work(user.id, info["code"], qty, info["price"], work_date)
    daily = await get_daily_total(user.id, work_date)
    day_total = sum(r[3] for r in daily)

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Записать ещё", callback_data="write_more")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
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


@router.callback_query(F.data == "write_more")
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


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()


# ==================== ИМПОРТ ИЗ SQLITE ====================

@router.message(F.document)
async def import_from_sqlite(message: types.Message):
    """Админ отправляет .db файл — бот переносит данные в PostgreSQL"""
    if message.from_user.id != ADMIN_ID:
        return

    if not message.document.file_name.endswith('.db'):
        await message.answer("❌ Отправьте файл с расширением .db")
        return

    await message.answer("⏳ Начинаю импорт данных...\n🧹 Очищаю старые данные...")

    import aiosqlite
    import tempfile
    import os
    from datetime import datetime, date as date_type

    def parse_datetime(value):
        if value is None:
            return None
        if isinstance(value, (datetime, date_type)):
            return value
        try:
            return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except:
            try:
                return datetime.strptime(value, '%Y-%m-%d')
            except:
                return None

    def parse_date_local(value):
        if value is None:
            return None
        if isinstance(value, date_type):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return datetime.strptime(value[:10], '%Y-%m-%d').date()
        except:
            return None

    try:
        file = await bot.get_file(message.document.file_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
            tmp_path = tmp.name

        await bot.download_file(file.file_path, tmp_path)
        sqlite = await aiosqlite.connect(tmp_path)

        from database import pool

        stats = {
            'workers': 0, 'categories': 0, 'prices': 0,
            'worker_cats': 0, 'work_logs': 0, 'advances': 0, 'penalties': 0
        }

        async with pool.acquire() as pg:
            # Очищаем таблицы
            await pg.execute("DELETE FROM work_log")
            await pg.execute("DELETE FROM advances")
            await pg.execute("DELETE FROM penalties")
            await pg.execute("DELETE FROM worker_categories")
            await pg.execute("DELETE FROM price_list")
            await pg.execute("DELETE FROM workers")
            await pg.execute("DELETE FROM categories")
            await pg.execute("DELETE FROM reminder_settings")

            # Сбрасываем счётчики
            await pg.execute("ALTER SEQUENCE IF EXISTS work_log_id_seq RESTART WITH 1")
            await pg.execute("ALTER SEQUENCE IF EXISTS advances_id_seq RESTART WITH 1")
            await pg.execute("ALTER SEQUENCE IF EXISTS penalties_id_seq RESTART WITH 1")

            # categories
            cursor = await sqlite.execute("SELECT code, name, emoji FROM categories")
            rows = await cursor.fetchall()
            for row in rows:
                await pg.execute(
                    "INSERT INTO categories (code, name, emoji) VALUES ($1, $2, $3)",
                    row[0], row[1], row[2])
            stats['categories'] = len(rows)

            # workers
            cursor = await sqlite.execute("SELECT telegram_id, name, registered_at FROM workers")
            rows = await cursor.fetchall()
            for row in rows:
                await pg.execute(
                    "INSERT INTO workers (telegram_id, name, registered_at) VALUES ($1, $2, $3)",
                    row[0], row[1], parse_datetime(row[2]))
            stats['workers'] = len(rows)

            # price_list
            cursor = await sqlite.execute("SELECT code, name, price, category_code, is_active FROM price_list")
            rows = await cursor.fetchall()
            for row in rows:
                await pg.execute(
                    "INSERT INTO price_list (code, name, price, category_code, is_active) VALUES ($1, $2, $3, $4, $5)",
                    row[0], row[1], row[2], row[3], bool(row[4]))
            stats['prices'] = len(rows)

            # worker_categories
            cursor = await sqlite.execute("SELECT worker_id, category_code FROM worker_categories")
            rows = await cursor.fetchall()
            for row in rows:
                await pg.execute(
                    "INSERT INTO worker_categories (worker_id, category_code) VALUES ($1, $2)",
                    row[0], row[1])
            stats['worker_cats'] = len(rows)

            # work_log
            cursor = await sqlite.execute(
                "SELECT worker_id, work_code, quantity, price_per_unit, total, work_date, created_at FROM work_log ORDER BY id")
            rows = await cursor.fetchall()
            for row in rows:
                await pg.execute(
                    "INSERT INTO work_log (worker_id, work_code, quantity, price_per_unit, total, work_date, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                    row[0], row[1], row[2], row[3], row[4],
                    parse_date_local(row[5]), parse_datetime(row[6]))
            stats['work_logs'] = len(rows)

            # advances
            cursor = await sqlite.execute(
                "SELECT worker_id, amount, comment, advance_date, created_at FROM advances ORDER BY id")
            rows = await cursor.fetchall()
            for row in rows:
                await pg.execute(
                    "INSERT INTO advances (worker_id, amount, comment, advance_date, created_at) VALUES ($1, $2, $3, $4, $5)",
                    row[0], row[1], row[2] or '', parse_date_local(row[3]), parse_datetime(row[4]))
            stats['advances'] = len(rows)

            # penalties
            cursor = await sqlite.execute(
                "SELECT worker_id, amount, reason, penalty_date, created_at FROM penalties ORDER BY id")
            rows = await cursor.fetchall()
            for row in rows:
                await pg.execute(
                    "INSERT INTO penalties (worker_id, amount, reason, penalty_date, created_at) VALUES ($1, $2, $3, $4, $5)",
                    row[0], row[1], row[2] or '', parse_date_local(row[3]), parse_datetime(row[4]))
            stats['penalties'] = len(rows)

            # reminder_settings
            cursor = await sqlite.execute("SELECT * FROM reminder_settings WHERE id = 1")
            settings = await cursor.fetchone()
            if settings:
                await pg.execute("""
                    INSERT INTO reminder_settings 
                    (id, evening_hour, evening_minute, late_hour, late_minute,
                     report_hour, report_minute, evening_enabled, late_enabled, report_enabled)
                    VALUES (1, $1, $2, $3, $4, $5, $6, $7, $8, $9)
                """, settings[1], settings[2], settings[3], settings[4],
                    settings[5], settings[6], bool(settings[7]), bool(settings[8]), bool(settings[9]))

        await sqlite.close()
        os.unlink(tmp_path)

        await message.answer(
            f"✅ Импорт завершён!\n\n"
            f"📊 Перенесено:\n"
            f"👥 Работников: {stats['workers']}\n"
            f"📂 Категорий: {stats['categories']}\n"
            f"💰 Позиций прайса: {stats['prices']}\n"
            f"🔗 Связей: {stats['worker_cats']}\n"
            f"📝 Записей работ: {stats['work_logs']}\n"
            f"💳 Авансов: {stats['advances']}\n"
            f"⚠️ Штрафов: {stats['penalties']}"
        )

    except Exception as e:
        logging.error(f"Import error: {e}")
        await message.answer(f"❌ Ошибка импорта: {e}")


# ==================== МОЙ БАЛАНС ====================

@router.message(F.text == "💳 Мой баланс")
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

@router.message(F.text == "📋 Мои записи")
async def my_entries(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📋 За какой день показать записи?",
        reply_markup=make_date_picker("viewdate", "myback")
    )
    await state.set_state(ViewEntries.choosing_date)


@router.callback_query(F.data.startswith("viewdate:"), ViewEntries.choosing_date)
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


@router.message(ViewEntries.entering_custom_date)
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

        # ✅ Исправлено — используем is_today()
        if is_today(target_date):
            buttons.append([InlineKeyboardButton(
                text=f"❌ {name} x {int(qty)} ({int(total)} руб)",
                callback_data=f"mydel:{entry_id}"
            )])

    text += f"\n💰 Итого: {int(day_total)} руб"
    if is_today(target_date) and buttons:
        text += "\n\nНажмите чтобы удалить:"

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="view_back")])

    if edit:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(WorkerDeleteEntry.choosing_entry)


@router.callback_query(F.data == "view_back")
async def view_entries_back(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📋 За какой день показать записи?",
        reply_markup=make_date_picker("viewdate", "myback")
    )
    await state.set_state(ViewEntries.choosing_date)
    await callback.answer()


@router.callback_query(F.data.startswith("mydel:"), WorkerDeleteEntry.choosing_entry)
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


@router.callback_query(F.data.startswith("myconf:"), WorkerDeleteEntry.confirming)
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


@router.callback_query(F.data == "myback")
async def my_entries_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Ок")
    await callback.answer()


# ==================== ЗАРАБОТОК ====================

@router.message(F.text == "💰 За сегодня")
async def show_daily(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    today = date.today()

    rows = await get_daily_total(uid)
    if not rows:
        await message.answer("📭 Сегодня нет записей.")
        return

    all_items = await get_price_list()
    names = {i[0]: i[1] for i in all_items}
    text = f"📊 {today.strftime('%d.%m.%Y')}:\n\n"
    total = 0
    for code, qty, price, sub in rows:
        text += f"▫️ {names.get(code, code)}: {int(qty)}шт x {int(price)} руб = {int(sub)} руб\n"
        total += sub
    text += f"\n💰 Итого за день: {int(total)} руб"

    stats = await get_worker_full_stats(uid, today.year, today.month)
    text += f"\n\n━━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 За {MONTHS_RU[today.month]}:\n"
    text += f"💰 Заработано: {int(stats['earned'])} руб\n"
    if stats['advances'] > 0:
        text += f"💳 Авансы: {int(stats['advances'])} руб\n"
    if stats['penalties'] > 0:
        text += f"⚠️ Штрафы: {int(stats['penalties'])} руб\n"
    text += f"📊 Остаток: {int(stats['balance'])} руб"

    await message.answer(text)


@router.message(F.text == "📊 За месяц")
async def show_monthly(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    today = date.today()
    rows = await get_monthly_by_days(uid, today.year, today.month)
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
    text += f"💰 Заработано: {int(grand_total)} руб\n"

    stats = await get_worker_full_stats(uid, today.year, today.month)
    if stats['advances'] > 0:
        text += f"💳 Авансы: {int(stats['advances'])} руб\n"
    if stats['penalties'] > 0:
        text += f"⚠️ Штрафы: {int(stats['penalties'])} руб\n"
    text += f"📊 К выплате: {int(stats['balance'])} руб"

    if work_days > 0:
        avg = grand_total / work_days
        text += f"\n📊 Среднее в день: {int(avg)} руб"

    await send_long_message(message, text)


# ==================== БЭКАП ====================

@router.message(F.text == "💾 Бэкап БД")
async def manual_backup(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    from bot import send_backup
    await send_backup(message.from_user.id)