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
    delete_entry_by_id, update_entry_quantity,
    get_worker_full_stats, get_worker_advances, get_worker_penalties
)
from states import WorkEntry, ViewEntries, WorkerDeleteEntry, WorkerEditEntry
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


def can_edit_date(date_value) -> bool:
    return True
    """Проверяет можно ли редактировать запись (сегодня или вчера)"""
    date_str = to_date_str(date_value)
    today = date.today()
    yesterday = today - timedelta(days=1)
    return date_str in (today.isoformat(), yesterday.isoformat())


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
            f"📁 {worker_cats[0][2]} {worker_cats[0][1]}\n\nВыберите работу:",
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
            f"📁 {worker_cats[0][2]} {worker_cats[0][1]}\n\nВыберите работу:",
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
    info = next(((c, n, p, cat, pt) for c, n, p, cat, pt in items if c == code), None)
    if not info:
        await callback.answer("Не найдено", show_alert=True)
        return

    price_type = info[4]
    await state.update_data(work_info={
        "code": info[0],
        "name": info[1],
        "price": info[2],
        "price_type": price_type
    })

    data = await state.get_data()

    if price_type == 'square':
        prompt = f"📅 Дата: {format_date(data['work_date'])}\n" \
                 f"{info[1]} ({int(info[2])} руб/м²)\n\nВведите площадь (м²):"
    else:
        prompt = f"📅 Дата: {format_date(data['work_date'])}\n" \
                 f"{info[1]} ({int(info[2])} руб/шт)\n\nВведите количество:"

    await callback.message.edit_text(prompt)
    await state.set_state(WorkEntry.entering_quantity)
    await callback.answer()


@router.message(WorkEntry.entering_quantity)
async def quantity_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    info = data["work_info"]
    price_type = info.get("price_type", "unit")

    try:
        if price_type == 'square':
            qty = float(message.text.replace(',', '.'))
        else:
            qty = int(message.text)

        if qty <= 0:
            raise ValueError
    except ValueError:
        if price_type == 'square':
            await message.answer("❌ Введите положительное число!\nПример: 12.5")
        else:
            await message.answer("❌ Введите положительное целое число!")
        return

    total = qty * info["price"]

    if total > 10000:
        await state.update_data(quantity=qty)
        buttons = [
            [InlineKeyboardButton(text="✅ Да, записать!", callback_data="confirm_large:yes")],
            [InlineKeyboardButton(text="✏️ Изменить количество", callback_data="confirm_large:edit")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_large:cancel")]
        ]

        unit_label = "м²" if price_type == 'square' else "шт"
        qty_display = f"{qty:.2f}" if price_type == 'square' else str(int(qty))

        await message.answer(
            f"⚠️ Внимание! Большая сумма!\n\n"
            f"📅 Дата: {format_date(data.get('work_date', date.today().isoformat()))}\n"
            f"📦 {info['name']} x {qty_display} {unit_label} = {int(total)} руб\n\nВсё верно?",
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
        data = await state.get_data()
        info = data["work_info"]
        price_type = info.get("price_type", "unit")

        if price_type == 'square':
            await callback.message.edit_text("Введите правильную площадь (м²):")
        else:
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
    price_type = info.get("price_type", "unit")

    total = await add_work(user.id, info["code"], qty, info["price"], work_date)
    daily = await get_daily_total(user.id, work_date)
    day_total = sum(r[3] for r in daily)

    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Записать ещё", callback_data="write_more")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])

    unit_label = "м²" if price_type == 'square' else "шт"
    qty_display = f"{qty:.2f}" if price_type == 'square' else str(int(qty))

    await message.answer(
        f"✅ Записано!\n\n"
        f"📅 Дата: {format_date(work_date)}\n"
        f"📦 {info['name']} x {qty_display} {unit_label} = {int(total)} руб\n"
        f"💰 За этот день: {int(day_total)} руб",
        reply_markup=buttons
    )

        if user.id != ADMIN_ID:
        notify_text = (
            f"📬 Новая запись!\n\n"
            f"👤 {user.full_name}\n"
            f"📅 {format_date(work_date)}\n"
            f"📦 {info['name']} x {qty_display} {unit_label} = {int(total)} руб\n"
            f"💰 За этот день: {int(day_total)} руб"
        )
        try:
            await bot.send_message(ADMIN_ID, notify_text)
        except Exception as e:
            logging.error(f"Notify admin: {e}")
        # Уведомления менеджерам отключены

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


# ==================== МОИ ЗАПИСИ (с редактированием и удалением) ====================

@router.message(F.text == "📁 Мои записи")
async def my_entries(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📁 За какой день показать записи?",
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
    can_edit = can_edit_date(target_date)

    await state.update_data(view_date=target_date)

    if not entries:
        text = f"📭 Нет записей за {date_str}"
        buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data="view_back")]]
        if edit:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await state.set_state(WorkerEditEntry.choosing_entry)
        return

    text = f"📁 Записи за {date_str}:\n\n"
    buttons = []
    day_total = 0

    for entry_id, name, cat_name, cat_emoji, qty, price, total, created, price_type in entries:
        time_str = created[11:16] if len(created) > 16 else ""
        unit_label = "м²" if price_type == 'square' else "шт"
        qty_display = f"{qty:.2f}" if price_type == 'square' else str(int(qty))

        text += f"{cat_emoji} {name} x {qty_display} {unit_label} = {int(total)} руб ({time_str})\n"
        day_total += total

        # Кнопки редактирования только для сегодня/вчера
        if can_edit:
            buttons.append([InlineKeyboardButton(
                text=f"✏️ {name} x {qty_display} {unit_label} ({int(total)} руб)",
                callback_data=f"wedit:{entry_id}"
            )])

    text += f"\n💰 Итого: {int(day_total)} руб"
    
    if can_edit and buttons:
        text += "\n\n✏️ Нажмите на запись для редактирования:"
    elif not can_edit:
        text += "\n\n⏰ Редактирование доступно только за сегодня и вчера"

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="view_back")])

    if edit:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(WorkerEditEntry.choosing_entry)


@router.callback_query(F.data == "view_back")
async def view_entries_back(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📁 За какой день показать записи?",
        reply_markup=make_date_picker("viewdate", "myback")
    )
    await state.set_state(ViewEntries.choosing_date)
    await callback.answer()


@router.callback_query(F.data.startswith("wedit:"), WorkerEditEntry.choosing_entry)
async def worker_entry_chosen(callback: types.CallbackQuery, state: FSMContext):
    entry_id = int(callback.data.split(":")[1])
    entry = await get_entry_by_id(entry_id)
    
    if not entry:
        await callback.answer("Не найдена", show_alert=True)
        await state.clear()
        return
    
    # Проверяем что это запись этого работника
    if entry[6] != callback.from_user.id:
        await callback.answer("Не ваша запись!", show_alert=True)
        await state.clear()
        return
    
    # Проверяем что можно редактировать
    if not can_edit_date(entry[5]):
        await callback.answer("Редактирование доступно только за сегодня и вчера", show_alert=True)
        return

    price_type = entry[8] if len(entry) > 8 else 'unit'
    unit_label = "м²" if price_type == 'square' else "шт"
    qty_display = f"{entry[2]:.2f}" if price_type == 'square' else str(int(entry[2]))

    await state.update_data(
        entry_id=entry_id, 
        entry_name=entry[1],
        entry_qty=entry[2], 
        entry_total=entry[4],
        entry_price=entry[3],
        entry_price_type=price_type,
        entry_date=entry[5]
    )
    
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить количество", callback_data="wact:edit")],
        [InlineKeyboardButton(text="🗑 Удалить запись", callback_data="wact:delete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="wact:back")]
    ]
    
    await callback.message.edit_text(
        f"📦 {entry[1]}\n\n"
        f"📅 {format_date(entry[5])}\n"
        f"🔢 Количество: {qty_display} {unit_label}\n"
        f"💵 Расценка: {int(entry[3])} руб/{unit_label}\n"
        f"💰 Сумма: {int(entry[4])} руб\n\n"
        f"Что сделать?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(WorkerEditEntry.choosing_action)
    await callback.answer()


@router.callback_query(F.data.startswith("wact:"), WorkerEditEntry.choosing_action)
async def worker_entry_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    data = await state.get_data()
    
    if action == "edit":
        price_type = data.get('entry_price_type', 'unit')
        if price_type == 'square':
            await callback.message.edit_text(
                f"📦 {data['entry_name']}\n"
                f"Текущее значение: {data['entry_qty']:.2f} м²\n\n"
                f"Введите новую площадь (м²):"
            )
        else:
            await callback.message.edit_text(
                f"📦 {data['entry_name']}\n"
                f"Текущее значение: {int(data['entry_qty'])} шт\n\n"
                f"Введите новое количество:"
            )
        await state.set_state(WorkerEditEntry.entering_new_quantity)
        
    elif action == "delete":
        price_type = data.get('entry_price_type', 'unit')
        unit_label = "м²" if price_type == 'square' else "шт"
        qty_display = f"{data['entry_qty']:.2f}" if price_type == 'square' else str(int(data['entry_qty']))
        
        buttons = [
            [InlineKeyboardButton(text="✅ Да, удалить!", callback_data="wdel:yes")],
            [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="wdel:no")]
        ]
        await callback.message.edit_text(
            f"⚠️ Удалить запись?\n\n"
            f"📦 {data['entry_name']} x {qty_display} {unit_label} = {int(data['entry_total'])} руб",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await state.set_state(WorkerEditEntry.confirming_delete)
        
    elif action == "back":
        target_date = data.get('view_date', date.today().isoformat())
        await show_entries_for_date(callback.message, state, 
                                    callback.from_user.id, target_date, edit=True)
    
    await callback.answer()


@router.message(WorkerEditEntry.entering_new_quantity)
async def worker_new_quantity(message: types.Message, state: FSMContext):
    data = await state.get_data()
    price_type = data.get('entry_price_type', 'unit')
    
    try:
        if price_type == 'square':
            new_qty = float(message.text.replace(',', '.'))
        else:
            new_qty = int(message.text)
        
        if new_qty <= 0:
            raise ValueError
    except ValueError:
        if price_type == 'square':
            await message.answer("❌ Введите положительное число!\nПример: 12.5")
        else:
            await message.answer("❌ Введите положительное целое число!")
        return
    
    entry_id = data['entry_id']
    old_qty = data['entry_qty']
    price = data['entry_price']
    old_total = data['entry_total']
    new_total = new_qty * price
    
    await update_entry_quantity(entry_id, new_qty)
    
    unit_label = "м²" if price_type == 'square' else "шт"
    old_qty_display = f"{old_qty:.2f}" if price_type == 'square' else str(int(old_qty))
    new_qty_display = f"{new_qty:.2f}" if price_type == 'square' else str(int(new_qty))
    
    await message.answer(
        f"✅ Изменено!\n\n"
        f"📦 {data['entry_name']}\n"
        f"Было: {old_qty_display} {unit_label} = {int(old_total)} руб\n"
        f"Стало: {new_qty_display} {unit_label} = {int(new_total)} руб",
        reply_markup=get_main_keyboard(message.from_user.id)
    )
    await state.clear()


@router.callback_query(F.data.startswith("wdel:"), WorkerEditEntry.confirming_delete)
async def worker_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.data.split(":")[1] == "yes":
        data = await state.get_data()
        deleted = await delete_entry_by_id(data["entry_id"])
        
        if deleted:
            price_type = data.get('entry_price_type', 'unit')
            unit_label = "м²" if price_type == 'square' else "шт"
            qty_display = f"{data['entry_qty']:.2f}" if price_type == 'square' else str(int(data['entry_qty']))
            
            await callback.message.edit_text(
                f"✅ Удалено!\n\n"
                f"📦 {data['entry_name']} x {qty_display} {unit_label} = {int(data['entry_total'])} руб"
            )
            
            # Уведомляем админа
            if callback.from_user.id != ADMIN_ID:
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"🗑 Работник удалил запись!\n\n"
                        f"👤 {callback.from_user.full_name}\n"
                        f"📦 {data['entry_name']} x {qty_display} {unit_label} = {int(data['entry_total'])} руб\n"
                        f"📅 {format_date(data.get('entry_date', ''))}"
                    )
                except Exception as e:
                    logging.error(f"Notify admin delete: {e}")
        else:
            await callback.message.edit_text("❌ Не найдена.")
    else:
        await callback.message.edit_text("❌ Отменено.")
    
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "myback")
async def my_entries_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Ок")
    await callback.answer()


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
            text += f"   ▪️ {format_date(adv_date)}: {int(amount)} руб"
            if comment:
                text += f" ({comment})"
            text += "\n"

    if penalties:
        text += f"\n⚠️ Штрафы:\n"
        for pen_id, amount, reason, pen_date, created in penalties:
            text += f"   ▪️ {format_date(pen_date)}: {int(amount)} руб"
            if reason:
                text += f" ({reason})"
            text += "\n"

    if stats['work_days'] > 0:
        avg = stats['earned'] / stats['work_days']
        text += f"\n📈 Среднее в день: {int(avg)} руб"

    await message.answer(text)


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
        text += f"▪️ {names.get(code, code)}: {int(qty)}шт x {int(price)} руб = {int(sub)} руб\n"
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
        text += f"   ▪️ {name} x {int(qty)} = {int(subtotal)} руб\n"
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
        text += f"\n📈 Среднее в день: {int(avg)} руб"

    await send_long_message(message, text)


# ==================== БЭКАП ====================

@router.message(F.text == "💾 Бэкап БД")
async def manual_backup(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    from bot import send_backup
    await send_backup(message.from_user.id)


# ==================== ИМПОРТ ИЗ JSON ====================

@router.message(F.document.file_name.endswith('.json'))
async def import_from_json(message: types.Message):
    """Админ отправляет .json файл — бот переносит данные в PostgreSQL"""
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("⏳ Начинаю импорт из JSON...\n🧹 Очищаю старые данные...")

    import tempfile
    import os
    import json
    from datetime import datetime, date as date_type

    def parse_datetime(value):
        if value is None:
            return None
        if isinstance(value, (datetime, date_type)):
            return value
        try:
            return datetime.fromisoformat(value)
        except:
            return None

    def parse_date_local(value):
        if value is None:
            return None
        if isinstance(value, date_type):
            return value
        try:
            return datetime.fromisoformat(value).date() if 'T' in value else datetime.strptime(value, '%Y-%m-%d').date()
        except:
            return None

    try:
        file = await bot.get_file(message.document.file_id)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8') as tmp:
            tmp_path = tmp.name

        await bot.download_file(file.file_path, tmp_path)

        with open(tmp_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        from database import pool

        stats = {
            'workers': 0, 'categories': 0, 'prices': 0,
            'worker_cats': 0, 'work_logs': 0, 'advances': 0, 'penalties': 0
        }

        async with pool.acquire() as pg:
            await pg.execute("DELETE FROM work_log")
            await pg.execute("DELETE FROM advances")
            await pg.execute("DELETE FROM penalties")
            await pg.execute("DELETE FROM worker_categories")
            await pg.execute("DELETE FROM price_list")
            await pg.execute("DELETE FROM workers")
            await pg.execute("DELETE FROM categories")
            await pg.execute("DELETE FROM reminder_settings")

            await pg.execute("ALTER SEQUENCE IF EXISTS work_log_id_seq RESTART WITH 1")
            await pg.execute("ALTER SEQUENCE IF EXISTS advances_id_seq RESTART WITH 1")
            await pg.execute("ALTER SEQUENCE IF EXISTS penalties_id_seq RESTART WITH 1")

            for row in data.get('categories', []):
                await pg.execute(
                    "INSERT INTO categories (code, name, emoji) VALUES ($1, $2, $3)",
                    row['code'], row['name'], row['emoji'])
            stats['categories'] = len(data.get('categories', []))

            for row in data.get('workers', []):
                await pg.execute(
                    "INSERT INTO workers (telegram_id, name, registered_at) VALUES ($1, $2, $3)",
                    row['telegram_id'], row['name'], parse_datetime(row['registered_at']))
            stats['workers'] = len(data.get('workers', []))

            for row in data.get('price_list', []):
                price_type = row.get('price_type', 'unit')
                await pg.execute(
                    "INSERT INTO price_list (code, name, price, price_type, category_code, is_active) VALUES ($1, $2, $3, $4, $5, $6)",
                    row['code'], row['name'], row['price'], price_type, row['category_code'], row.get('is_active', True))
            stats['prices'] = len(data.get('price_list', []))

            for row in data.get('worker_categories', []):
                await pg.execute(
                    "INSERT INTO worker_categories (worker_id, category_code) VALUES ($1, $2)",
                    row['worker_id'], row['category_code'])
            stats['worker_cats'] = len(data.get('worker_categories', []))

            for row in data.get('work_log', []):
                await pg.execute(
                    "INSERT INTO work_log (worker_id, work_code, quantity, price_per_unit, total, work_date, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                    row['worker_id'], row['work_code'], row['quantity'], row['price_per_unit'], row['total'],
                    parse_date_local(row['work_date']), parse_datetime(row['created_at']))
            stats['work_logs'] = len(data.get('work_log', []))

            for row in data.get('advances', []):
                await pg.execute(
                    "INSERT INTO advances (worker_id, amount, comment, advance_date, created_at) VALUES ($1, $2, $3, $4, $5)",
                    row['worker_id'], row['amount'], row.get('comment', ''),
                    parse_date_local(row['advance_date']), parse_datetime(row['created_at']))
            stats['advances'] = len(data.get('advances', []))

            for row in data.get('penalties', []):
                await pg.execute(
                    "INSERT INTO penalties (worker_id, amount, reason, penalty_date, created_at) VALUES ($1, $2, $3, $4, $5)",
                    row['worker_id'], row['amount'], row.get('reason', ''),
                    parse_date_local(row['penalty_date']), parse_datetime(row['created_at']))
            stats['penalties'] = len(data.get('penalties', []))

            for row in data.get('reminder_settings', []):
                await pg.execute("""
                    INSERT INTO reminder_settings
                    (id, evening_hour, evening_minute, late_hour, late_minute,
                     report_hour, report_minute, evening_enabled, late_enabled, report_enabled)
                    VALUES (1, $1, $2, $3, $4, $5, $6, $7, $8, $9)
                """, row['evening_hour'], row['evening_minute'], row['late_hour'], row['late_minute'],
                    row['report_hour'], row['report_minute'], row['evening_enabled'], row['late_enabled'], row['report_enabled'])

        os.unlink(tmp_path)

        await message.answer(
            f"✅ Импорт из JSON завершён!\n\n"
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
        logging.error(f"JSON Import error: {e}")
        await message.answer(f"❌ Ошибка импорта: {e}")