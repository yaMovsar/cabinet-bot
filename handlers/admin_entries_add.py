"""
Админ вносит запись работы ЗА работника (в т.ч. за «деда» без Telegram).

Вход — кнопка «➕ Добавить запись» в «🔧 Записи работников» после выбора
работника и месяца. Дата — любая внутри выбранного месяца (закрытие месяца
на админа не действует). Расценка берётся текущая, как при обычной записи.
"""

import calendar
import logging
from datetime import date

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import add_work, get_price_list_for_worker, get_worker_categories
from states import AdminManageEntries
from keyboards import make_work_buttons
from utils import format_date, format_qty, unit_of, format_qty_unit, MONTHS_RU, SIDE_JOB_TYPE
from handlers.admin import admin_entries_show

router = Router()

S = AdminManageEntries


def _nav(back_cb: str = "aea_back_list") -> list:
    return [
        [InlineKeyboardButton(text="🔙 К записям", callback_data=back_cb)],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ae_cancel")],
    ]


def _date_kb(year: int, month: int) -> InlineKeyboardMarkup:
    today = date.today()
    last_day = calendar.monthrange(year, month)[1]
    rows = []
    if (year, month) == (today.year, today.month):
        rows.append([InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data=f"aea_d:{today.isoformat()}")])
        if today.day > 1:
            y = date(year, month, today.day - 1)
            rows.append([InlineKeyboardButton(
                text=f"📅 Вчера ({y.strftime('%d.%m')})",
                callback_data=f"aea_d:{y.isoformat()}")])
    else:
        d = date(year, month, last_day)
        rows.append([InlineKeyboardButton(
            text=f"📅 Последний день ({d.strftime('%d.%m')})",
            callback_data=f"aea_d:{d.isoformat()}")])
    rows.extend(_nav())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _header(data: dict) -> str:
    text = f"👤 <b>{data['worker_name']}</b>\n"
    if data.get("add_date"):
        text += f"📅 {format_date(data['add_date'])}\n"
    return text


# ==================== СТАРТ ====================

@router.callback_query(F.data == "aea_start", S.viewing_entries)
@router.callback_query(F.data == "aea_start", S.choosing_month)
async def add_start(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("worker_id") or not data.get("year"):
        await callback.answer("Сессия сброшена — откройте «🔧 Записи работников» заново", show_alert=True)
        return

    items = await get_price_list_for_worker(data["worker_id"])
    if not items:
        await callback.answer(
            "У работника нет категорий.\nНазначьте: ✏️ Редактировать → 🔗 Назначить кат.",
            show_alert=True)
        return

    year, month = data["year"], data["month"]
    await state.update_data(add_date=None, add_info=None, add_qty=None, add_comment="")
    await callback.message.edit_text(
        _header(data) +
        f"\n➕ Новая запись за {MONTHS_RU[month]} {year}\n\n"
        f"Выберите день кнопкой или напишите число месяца (например: <b>15</b>):",
        reply_markup=_date_kb(year, month),
        parse_mode="HTML",
    )
    await state.set_state(S.add_choosing_date)
    await callback.answer()


# ==================== ДАТА ====================

async def _date_chosen(target, state: FSMContext, chosen: date, edit: bool):
    await state.update_data(add_date=chosen.isoformat())
    data = await state.get_data()
    cats = await get_worker_categories(data["worker_id"])

    if len(cats) == 1:
        await _show_works(target, state, cats[0][0], edit)
        return

    buttons = [[InlineKeyboardButton(text=f"{emoji} {name}", callback_data=f"aea_c:{code}")]
               for code, name, emoji in cats]
    buttons.extend(_nav())
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = _header(data) + "\n📂 Выберите категорию:"
    if edit:
        await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(S.add_choosing_category)


@router.callback_query(F.data.startswith("aea_d:"), S.add_choosing_date)
async def add_date_button(callback: types.CallbackQuery, state: FSMContext):
    chosen = date.fromisoformat(callback.data.split(":", 1)[1])
    await _date_chosen(callback.message, state, chosen, edit=True)
    await callback.answer()


@router.message(S.add_choosing_date)
async def add_date_typed(message: types.Message, state: FSMContext):
    data = await state.get_data()
    year, month = data["year"], data["month"]
    last_day = calendar.monthrange(year, month)[1]
    try:
        day = int(message.text.strip().split(".")[0])
        if not 1 <= day <= last_day:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer(f"❌ Введите число от 1 до {last_day}")
        return

    chosen = date(year, month, day)
    if chosen > date.today():
        await message.answer("❌ Нельзя записать на будущую дату!")
        return
    await _date_chosen(message, state, chosen, edit=False)


# ==================== КАТЕГОРИЯ / РАБОТА ====================

async def _show_works(target, state: FSMContext, cat_code: str, edit: bool):
    data = await state.get_data()
    items = await get_price_list_for_worker(data["worker_id"])
    cat_items = [i for i in items if i[3] == cat_code]
    buttons = make_work_buttons(cat_items)
    buttons.extend(_nav())
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = _header(data) + "\n📦 Выберите работу:"
    if edit:
        await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(S.add_choosing_work)


@router.callback_query(F.data.startswith("aea_c:"), S.add_choosing_category)
async def add_category_chosen(callback: types.CallbackQuery, state: FSMContext):
    await _show_works(callback.message, state, callback.data.split(":", 1)[1], edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("work:"), S.add_choosing_work)
async def add_work_chosen(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    data = await state.get_data()
    items = await get_price_list_for_worker(data["worker_id"])
    info = next((i for i in items if i[0] == code), None)
    if not info:
        await callback.answer("Работа не найдена", show_alert=True)
        return

    code, name, price, _cat, price_type = info
    await state.update_data(add_info={"code": code, "name": name, "price": price, "price_type": price_type})

    if price_type == SIDE_JOB_TYPE:
        prompt = f"💵 {name}\n\nВведите сумму в рублях:"
    elif price_type == 'square':
        prompt = f"📦 {name} ({int(price)} ₽/м²)\n\nВведите площадь (м²):"
    else:
        prompt = f"📦 {name} ({int(price)} ₽/шт)\n\nВведите количество:"

    await callback.message.edit_text(_header(data) + "\n" + prompt, parse_mode="HTML")
    await state.set_state(S.add_entering_qty)
    await callback.answer()


# ==================== КОЛИЧЕСТВО / СУММА ====================

@router.message(S.add_entering_qty)
async def add_qty_entered(message: types.Message, state: FSMContext):
    data = await state.get_data()
    info = data.get("add_info")
    price_type = info["price_type"]
    raw = (message.text or "").replace(",", ".").replace(" ", "")
    try:
        if price_type == 'square':
            qty = float(raw)
        elif price_type == SIDE_JOB_TYPE:
            qty = round(float(raw))
        else:
            qty = int(raw)
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число!")
        return

    await state.update_data(add_qty=qty)

    if price_type == SIDE_JOB_TYPE:
        await message.answer(
            f"💵 Сумма: {format_qty_unit(qty, price_type)}\n\n"
            f"✏️ Коротко опишите, что за шабашка\n(или «-», если без описания):"
        )
        await state.set_state(S.add_entering_comment)
        return

    await _show_confirm(message, state)


@router.message(S.add_entering_comment)
async def add_comment_entered(message: types.Message, state: FSMContext):
    comment = (message.text or "").strip()
    if comment == "-":
        comment = ""
    await state.update_data(add_comment=comment[:200])
    await _show_confirm(message, state)


# ==================== ПОДТВЕРЖДЕНИЕ ====================

def _work_line(info: dict, qty, comment: str) -> str:
    price_type = info["price_type"]
    total = qty * info["price"]
    if price_type == SIDE_JOB_TYPE:
        line = f"💵 {info['name']}: {int(total)} ₽"
        if comment:
            line += f"\n📝 {comment}"
        return line
    return (f"📦 {info['name']} × {format_qty(qty, price_type)} {unit_of(price_type)}"
            f" = {int(total)} ₽")


async def _show_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Записать", callback_data="aea_ok")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="aea_back_list")],
    ])
    await message.answer(
        _header(data) + "\n" +
        _work_line(data["add_info"], data["add_qty"], data.get("add_comment", "")) +
        "\n\nЗаписать за работника?",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await state.set_state(S.add_confirming)


@router.callback_query(F.data == "aea_ok", S.add_confirming)
async def add_confirmed(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    info = data["add_info"]
    comment = data.get("add_comment", "") if info["price_type"] == SIDE_JOB_TYPE else ""
    try:
        await add_work(data["worker_id"], info["code"], data["add_qty"], info["price"],
                       data["add_date"], comment)
    except Exception as e:
        logging.exception(f"Admin add entry error: {e}")
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ещё запись", callback_data="aea_start")],
        [InlineKeyboardButton(text="📁 К записям", callback_data="aea_back_list")],
    ])
    await callback.message.edit_text(
        "✅ Записано!\n\n" + _header(data) +
        _work_line(info, data["add_qty"], comment),
        reply_markup=kb,
        parse_mode="HTML",
    )
    await state.set_state(S.viewing_entries)
    await callback.answer()


# ==================== НАЗАД К СПИСКУ ====================

@router.callback_query(F.data == "aea_back_list")
async def add_back_to_list(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("worker_id") or not data.get("year"):
        await callback.message.edit_text("👌 Ок")
        await state.clear()
        await callback.answer()
        return
    await admin_entries_show(callback, state, data["year"], data["month"])
