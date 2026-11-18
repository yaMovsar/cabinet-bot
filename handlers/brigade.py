"""
Доля управляющего с работы бригады.

Управляющий (напр. Адам) получает фиксированную сумму с каждой единицы работы,
сделанной бригадой: 100 ₽ с упаковки большой двери, 50 ₽ с антресоли и т.д.
Ставка задаётся на каждый вид работы. Когда работник записывает работу, бот сам
создаёт управляющему запись «… (с бригады)» — она правится и удаляется вместе
с записью работника.

Админ-панель → ✏️ Редактировать → 👔 Доля управляющего
"""

from datetime import date

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import (
    get_brigade_manager_id, set_brigade_manager_id,
    set_work_manager_rate, get_manager_rate_works, get_works_for_manager_rate,
    backfill_manager_shares, get_manager_share_total,
    get_categories, get_all_workers, get_worker, get_work_by_code,
)
from states import AdminBrigadeShare
from handlers.filters import AdminFilter
from utils import MONTHS_RU, unit_of, is_admin, safe_edit_text

router = Router()


def _money(value) -> str:
    return f"{int(value):,}".replace(",", " ")


def _rate_text(rate, price_type) -> str:
    rate = float(rate)
    shown = int(rate) if rate == int(rate) else round(rate, 2)
    return f"{shown} ₽/{unit_of(price_type)}"


async def _home_view():
    """Главный экран: кто получает, ставки, сколько начислено за месяц"""
    today = date.today()
    manager_id = await get_brigade_manager_id()
    works = await get_manager_rate_works()

    text = "👔 Доля управляющего с работы бригады\n\n"
    if manager_id:
        worker = await get_worker(manager_id)
        name = worker['name'] if worker else str(manager_id)
        text += f"👤 Получатель: {name}\n"
    else:
        text += "👤 Получатель не выбран — начисления выключены\n"

    if works:
        text += "\n💵 Ставки (за 1 ед. работы бригады):\n"
        for _code, name, emoji, _cat, rate, price_type in works:
            text += f"{emoji} {name} — {_rate_text(rate, price_type)}\n"
    else:
        text += "\n💵 Ставки ещё не заданы\n"

    if manager_id:
        total = await get_manager_share_total(today.year, today.month)
        text += f"\n📊 Начислено за {MONTHS_RU[today.month].lower()}: {_money(total)} ₽\n"

    text += ("\nℹ️ Когда работник записывает работу, получателю автоматически "
             "создаётся запись «… (с бригады)». Работник изменил или удалил "
             "свою запись — доля меняется вместе с ней.")

    buttons = [
        [InlineKeyboardButton(text="💵 Задать ставку", callback_data="bm:rate")],
        [InlineKeyboardButton(
            text="👤 Сменить получателя" if manager_id else "👤 Выбрать получателя",
            callback_data="bm:who")],
    ]
    if manager_id:
        buttons.append([InlineKeyboardButton(
            text=f"🔄 Доначислить за {MONTHS_RU[today.month].lower()}",
            callback_data="bm:fill")])
        buttons.append([InlineKeyboardButton(
            text="⛔ Выключить начисления", callback_data="bm:off")])
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def _back_home_row():
    return [InlineKeyboardButton(text="🔙 Назад", callback_data="bm:home")]


async def _show_home(callback: types.CallbackQuery, prefix: str = ""):
    text, kb = await _home_view()
    await safe_edit_text(callback.message, prefix + text, reply_markup=kb)


# ==================== ВХОД ====================

@router.message(F.text == "👔 Доля управляющего", AdminFilter())
async def brigade_share_start(message: types.Message, state: FSMContext):
    await state.clear()
    text, kb = await _home_view()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "bm:home")
async def brigade_home(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    await _show_home(callback)
    await callback.answer()


# ==================== ПОЛУЧАТЕЛЬ ====================

@router.callback_query(F.data == "bm:who")
async def brigade_choose_manager(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    current = await get_brigade_manager_id()
    buttons = [
        [InlineKeyboardButton(text=("✅ " if wid == current else "") + name,
                              callback_data=f"bm_set:{wid}")]
        for wid, name in await get_all_workers()
    ]
    buttons.append(_back_home_row())
    await safe_edit_text(
        callback.message,
        "👤 Кто получает долю с работы бригады?\n\n"
        "Уже начисленные записи останутся у прежнего получателя — "
        "новому пойдёт только то, что запишут после смены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("bm_set:"))
async def brigade_set_manager(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    wid = int(callback.data.split(":")[1])
    worker = await get_worker(wid)
    if not worker:
        return await callback.answer("❌ Работник не найден", show_alert=True)
    await set_brigade_manager_id(wid)
    await _show_home(callback, f"✅ Получатель: {worker['name']}\n\n")
    await callback.answer()


@router.callback_query(F.data == "bm:off")
async def brigade_off(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await set_brigade_manager_id(None)
    await _show_home(callback, "⛔ Начисления выключены. Уже начисленное не тронуто.\n\n")
    await callback.answer()


# ==================== ДОНАЧИСЛИТЬ ====================

@router.callback_query(F.data == "bm:fill")
async def brigade_backfill(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    today = date.today()
    result = await backfill_manager_shares(today.year, today.month)
    if result['count']:
        prefix = (f"✅ Доначислено записей: {result['count']} "
                  f"на {_money(result['total'])} ₽\n\n")
    else:
        prefix = "✅ Всё уже начислено — добавлять нечего.\n\n"
    await _show_home(callback, prefix)


# ==================== СТАВКИ ====================

@router.callback_query(F.data == "bm:rate")
async def brigade_rate_categories(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    buttons = [
        [InlineKeyboardButton(text=f"{emoji} {name}", callback_data=f"bm_cat:{code}")]
        for code, name, emoji in await get_categories()
    ]
    buttons.append(_back_home_row())
    await safe_edit_text(callback.message, "💵 Выберите категорию:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


async def _show_category_works(callback: types.CallbackQuery, cat_code: str):
    works = await get_works_for_manager_rate(cat_code)
    if not works:
        await callback.answer("В этой категории нет видов работ", show_alert=True)
        return
    buttons = []
    for code, name, rate, price_type in works:
        label = f"{name} — {_rate_text(rate, price_type)}" if rate > 0 else f"{name} — нет"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"bm_w:{code}")])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:rate")])
    await safe_edit_text(callback.message,
                         "💵 Выберите вид работы\n(справа — сколько получает управляющий):",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("bm_cat:"))
async def brigade_rate_works(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    await _show_category_works(callback, callback.data.split(":", 1)[1])


@router.callback_query(F.data.startswith("bm_w:"))
async def brigade_rate_ask(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    code = callback.data.split(":", 1)[1]
    work = await get_work_by_code(code)
    if not work:
        return await callback.answer("❌ Работа не найдена", show_alert=True)
    # work: code, name, price, price_type, category_code, cat_name, emoji
    await state.set_state(AdminBrigadeShare.entering_rate)
    await state.update_data(bm_code=code, bm_cat=work[4])
    await safe_edit_text(
        callback.message,
        f"💵 {work[6]} {work[1]}\n\n"
        f"Сколько получает управляющий за 1 {unit_of(work[3])}, сделанную бригадой?\n"
        f"Введите сумму в рублях (0 — не начислять).\n\n"
        f"Новая ставка действует на новые записи; уже начисленное не меняется.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"bm_cat:{work[4]}")]
        ]))
    await callback.answer()


@router.message(AdminBrigadeShare.entering_rate)
async def brigade_rate_entered(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        rate = float((message.text or "").replace(",", ".").replace(" ", ""))
        if rate < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число, например 100 (или 0, чтобы убрать)")
        return
    data = await state.get_data()
    code = data.get("bm_code")
    await state.clear()
    if not code:
        await message.answer("⚠️ Сессия сброшена — откройте «👔 Доля управляющего» заново.")
        return
    await set_work_manager_rate(code, rate)
    text, kb = await _home_view()
    done = "✅ Ставка убрана" if rate == 0 else "✅ Ставка сохранена"
    await message.answer(f"{done}\n\n{text}", reply_markup=kb)
