from datetime import date

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import (
    add_expense, get_expenses, get_expenses_total, get_expense_by_id,
    update_expense_amount, set_expense_recurring, delete_expense,
    get_month_cash_need
)
from states import AdminExpense
from utils import MONTHS_RU
from handlers.filters import AdminFilter

router = Router()

# Частые названия — чтобы не набирать руками
PRESETS = ["Аренда", "Свет", "Вода", "Интернет", "Материалы", "Инструмент", "Вывоз мусора"]


def _money(value) -> str:
    return f"{int(value):,}".replace(",", " ")


def _prev_month(year: int, month: int):
    return (year - 1, 12) if month == 1 else (year, month - 1)


async def _render_expenses(target, state: FSMContext, year: int, month: int, edit=False):
    """Список расходов за месяц с итогом"""
    items = await get_expenses(year, month)
    total = await get_expenses_total(year, month)
    await state.update_data(year=year, month=month)

    text = f"🧾 <b>Расходы цеха — {MONTHS_RU[month]} {year}</b>\n\n"
    if not items:
        text += "Пока пусто.\n\nНажмите «➕ Добавить расход».\n"
    else:
        for _eid, name, amount, _dt, comment, is_recurring in items:
            mark = "🔁 " if is_recurring else ""
            text += f"{mark}{name}: <b>{_money(amount)} ₽</b>\n"
            if comment:
                text += f"    <i>{comment}</i>\n"
        text += f"\n💰 <b>Итого расходов: {_money(total)} ₽</b>"

    buttons = [[InlineKeyboardButton(text="➕ Добавить расход", callback_data="exp_add")]]
    for eid, name, amount, _dt, _c, is_recurring in items:
        mark = "🔁 " if is_recurring else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{name} — {_money(amount)} ₽",
            callback_data=f"exp_item:{eid}"
        )])

    py, pm = _prev_month(year, month)
    today = date.today()
    if (year, month) == (today.year, today.month):
        buttons.append([InlineKeyboardButton(
            text=f"📅 {MONTHS_RU[pm]} {py}", callback_data=f"exp_month:{py}:{pm}")])
    else:
        buttons.append([InlineKeyboardButton(
            text=f"📅 {MONTHS_RU[today.month]} {today.year} (текущий)",
            callback_data=f"exp_month:{today.year}:{today.month}")])
    buttons.append([InlineKeyboardButton(text="💰 Сколько готовить денег", callback_data="exp_need")])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="exp_close")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(AdminExpense.viewing)


# ==================== СПИСОК ====================

@router.message(F.text == "🧾 Расходы", AdminFilter())
async def expenses_menu(message: types.Message, state: FSMContext):
    await state.clear()
    today = date.today()
    await _render_expenses(message, state, today.year, today.month)


@router.callback_query(F.data.startswith("exp_month:"), AdminExpense.viewing)
async def expenses_month(callback: types.CallbackQuery, state: FSMContext):
    _, year, month = callback.data.split(":")
    await _render_expenses(callback.message, state, int(year), int(month), edit=True)
    await callback.answer()


@router.callback_query(F.data == "exp_close", AdminExpense.viewing)
async def expenses_close(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Ок")
    await callback.answer()


# ==================== СКОЛЬКО ГОТОВИТЬ ДЕНЕГ ====================

async def build_cash_need_text(year: int = None, month: int = None) -> str:
    need = await get_month_cash_need(year, month)
    year, month = need['year'], need['month']
    items = await get_expenses(year, month)

    text = (
        f"💰 <b>Сколько нужно денег — {MONTHS_RU[month]} {year}</b>\n\n"
        f"👷 Зарплата к выплате: <b>{_money(need['salary'])} ₽</b>\n"
        f"🧾 Расходы цеха: <b>{_money(need['expenses'])} ₽</b>\n"
    )
    if items:
        for _eid, name, amount, _dt, _c, is_recurring in items:
            mark = "🔁 " if is_recurring else ""
            text += f"    {mark}{name}: {_money(amount)} ₽\n"
    else:
        text += "    <i>расходы не внесены</i>\n"

    text += (
        f"─────────────────\n"
        f"📦 <b>ВСЕГО ГОТОВИТЬ: {_money(need['total'])} ₽</b>\n\n"
        f"<i>Зарплата — по записям на текущий момент, до конца месяца вырастет.</i>"
    )
    return text


@router.message(F.text == "💰 Сколько готовить денег", AdminFilter())
async def cash_need_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(await build_cash_need_text(), parse_mode="HTML")


@router.callback_query(F.data == "exp_need", AdminExpense.viewing)
async def cash_need_inline(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = await build_cash_need_text(data.get("year"), data.get("month"))
    buttons = [[InlineKeyboardButton(text="🔙 К расходам", callback_data="exp_back_list")]]
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "exp_back_list")   # доступна с любого шага
async def expenses_back_list(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    today = date.today()
    await _render_expenses(callback.message, state,
                           data.get("year", today.year), data.get("month", today.month),
                           edit=True)
    await callback.answer()


# ==================== ДОБАВЛЕНИЕ ====================

@router.callback_query(F.data == "exp_add", AdminExpense.viewing)
async def expense_add_start(callback: types.CallbackQuery, state: FSMContext):
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"exp_preset:{name}")]
               for name in PRESETS]
    buttons.append([InlineKeyboardButton(text="✏️ Своё название", callback_data="exp_preset:")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="exp_back_list")])
    await callback.message.edit_text(
        "🧾 За что расход?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await state.set_state(AdminExpense.choosing_name)
    await callback.answer()


@router.callback_query(F.data.startswith("exp_preset:"), AdminExpense.choosing_name)
async def expense_preset(callback: types.CallbackQuery, state: FSMContext):
    name = callback.data.split(":", 1)[1]
    if not name:
        await callback.message.edit_text("✏️ Введите название расхода:")
        await state.set_state(AdminExpense.entering_name)
        await callback.answer()
        return
    await state.update_data(name=name)
    await callback.message.edit_text(f"🧾 {name}\n\n💰 Введите сумму в рублях:")
    await state.set_state(AdminExpense.entering_amount)
    await callback.answer()


@router.message(AdminExpense.entering_name)
async def expense_name_entered(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ Слишком коротко. Введите название расхода:")
        return
    await state.update_data(name=name[:60])
    await message.answer(f"🧾 {name[:60]}\n\n💰 Введите сумму в рублях:")
    await state.set_state(AdminExpense.entering_amount)


@router.message(AdminExpense.entering_amount)
async def expense_amount_entered(message: types.Message, state: FSMContext):
    try:
        amount = round(float(message.text.replace(",", ".").replace(" ", "")))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите сумму числом!\nПример: 45000")
        return

    await state.update_data(amount=amount)
    data = await state.get_data()
    buttons = [
        [InlineKeyboardButton(text="🔁 Да, каждый месяц", callback_data="exp_rec:yes")],
        [InlineKeyboardButton(text="1️⃣ Нет, разовый", callback_data="exp_rec:no")],
    ]
    await message.answer(
        f"🧾 {data['name']}: {_money(amount)} ₽\n\n"
        f"Этот расход повторяется каждый месяц?\n"
        f"<i>Постоянные (аренда, свет) бот сам подставит 1-го числа с этой же суммой — "
        f"останется только поправить, если изменилась.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await state.set_state(AdminExpense.choosing_recurring)


@router.callback_query(F.data.startswith("exp_rec:"), AdminExpense.choosing_recurring)
async def expense_recurring_chosen(callback: types.CallbackQuery, state: FSMContext):
    is_recurring = callback.data.split(":")[1] == "yes"
    data = await state.get_data()
    today = date.today()
    year = data.get("year", today.year)
    month = data.get("month", today.month)
    # расход пишем в выбранный месяц; в текущем — сегодняшним числом
    when = today if (year, month) == (today.year, today.month) else date(year, month, 1)

    await add_expense(data["name"], data["amount"], when, is_recurring=is_recurring)
    await callback.answer("✅ Записано")
    await _render_expenses(callback.message, state, year, month, edit=True)


# ==================== КАРТОЧКА РАСХОДА ====================

@router.callback_query(F.data.startswith("exp_item:"), AdminExpense.viewing)
async def expense_item(callback: types.CallbackQuery, state: FSMContext):
    eid = int(callback.data.split(":")[1])
    item = await get_expense_by_id(eid)
    if not item:
        await callback.answer("❌ Расход не найден", show_alert=True)
        return
    _id, name, amount, dt, comment, is_recurring = item
    await state.update_data(expense_id=eid)

    text = (
        f"🧾 <b>{name}</b>\n\n"
        f"💰 Сумма: {_money(amount)} ₽\n"
        f"📅 Дата: {dt[8:10]}.{dt[5:7]}.{dt[0:4]}\n"
        f"🔁 Постоянный: {'да' if is_recurring else 'нет'}"
    )
    if comment:
        text += f"\n📝 {comment}"

    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data="exp_edit")],
        [InlineKeyboardButton(
            text="1️⃣ Сделать разовым" if is_recurring else "🔁 Сделать постоянным",
            callback_data="exp_toggle")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="exp_del")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="exp_back_list")],
    ]
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "exp_edit", AdminExpense.viewing)
async def expense_edit_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✏️ Введите новую сумму (₽):")
    await state.set_state(AdminExpense.editing_amount)
    await callback.answer()


@router.message(AdminExpense.editing_amount)
async def expense_edit_done(message: types.Message, state: FSMContext):
    try:
        amount = round(float(message.text.replace(",", ".").replace(" ", "")))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите сумму числом!\nПример: 45000")
        return

    data = await state.get_data()
    item = await get_expense_by_id(data.get("expense_id"))
    if not item:
        await message.answer("❌ Расход не найден.")
        await state.clear()
        return

    await update_expense_amount(item[0], amount)
    await message.answer(
        f"✅ Изменено!\n\n🧾 {item[1]}\nБыло: {_money(item[2])} ₽\nСтало: {_money(amount)} ₽")
    today = date.today()
    await _render_expenses(message, state,
                           data.get("year", today.year), data.get("month", today.month))


@router.callback_query(F.data == "exp_toggle", AdminExpense.viewing)
async def expense_toggle(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    item = await get_expense_by_id(data.get("expense_id"))
    if not item:
        await callback.answer("❌ Расход не найден", show_alert=True)
        return
    new_val = not item[5]
    await set_expense_recurring(item[0], new_val)
    await callback.answer("🔁 Теперь постоянный" if new_val else "1️⃣ Теперь разовый")
    today = date.today()
    await _render_expenses(callback.message, state,
                           data.get("year", today.year), data.get("month", today.month),
                           edit=True)


@router.callback_query(F.data == "exp_del", AdminExpense.viewing)
async def expense_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    item = await get_expense_by_id(data.get("expense_id"))
    if not item:
        await callback.answer("❌ Расход не найден", show_alert=True)
        return
    buttons = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data="exp_del_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="exp_back_list")],
    ]
    await callback.message.edit_text(
        f"⚠️ Удалить расход?\n\n🧾 {item[1]}: {_money(item[2])} ₽",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data == "exp_del_yes", AdminExpense.viewing)
async def expense_delete_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    deleted = await delete_expense(data.get("expense_id"))
    if deleted:
        await callback.answer(f"🗑 Удалено: {deleted[0]}")
    today = date.today()
    await _render_expenses(callback.message, state,
                           data.get("year", today.year), data.get("month", today.month),
                           edit=True)
