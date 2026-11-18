"""
Доля управляющих с работы бригады.

Управляющие получают фиксированную сумму с каждой единицы работы бригады:
100 ₽ с упаковки большой двери, 50 ₽ с антресоли и т.д.
  • управляющий назначается на категорию: кровати → один, шкафы → другой,
    комоды и тумбы → третий;
  • ставка задаётся на каждый вид работы.
Когда работник записывает работу, бот сам создаёт управляющему его категории
запись «… (с бригады)» — она правится и удаляется вместе с записью работника.

Админ-панель → ✏️ Редактировать → 👔 Доля управляющего
"""

from datetime import date

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import (
    set_category_share_manager, get_share_categories, get_categories_with_share_manager,
    set_work_manager_rate, get_works_for_manager_rate,
    backfill_manager_shares, get_manager_share_totals,
    get_all_workers, get_worker, get_work_by_code,
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
    """Главный экран: категории → управляющий и ставки, начислено за месяц"""
    today = date.today()
    month = MONTHS_RU[today.month].lower()
    cats = await get_share_categories()

    text = "👔 Доля управляющих с работы бригады\n"
    if not cats:
        text += "\nПока ничего не настроено.\n"
    for cat in cats:
        who = f"👤 {cat['manager_name']}" if cat['manager_name'] else "👤 не назначен"
        text += f"\n{cat['emoji']} {cat['name']} → {who}\n"
        if cat['works']:
            for name, rate, price_type in cat['works']:
                text += f"   • {name} — {_rate_text(rate, price_type)}\n"
        else:
            text += "   • ставок нет\n"
        if cat['works'] and not cat['manager_name']:
            text += "   ⚠️ без управляющего — не начисляется\n"

    totals = await get_manager_share_totals(today.year, today.month)
    if totals:
        text += f"\n📊 Начислено за {month}:\n"
        for name, total in totals:
            text += f"   {name}: {_money(total)} ₽\n"

    text += ("\nℹ️ Когда работник записывает работу, управляющему его категории "
             "автоматически создаётся запись «… (с бригады)». Работник изменил или "
             "удалил свою запись — доля меняется вместе с ней.")

    buttons = [
        [InlineKeyboardButton(text="👤 Назначить управляющего", callback_data="bm:who")],
        [InlineKeyboardButton(text="💵 Задать ставку", callback_data="bm:rate")],
        [InlineKeyboardButton(text=f"🔄 Доначислить за {month}", callback_data="bm:fill")],
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def _back_home_row():
    return [InlineKeyboardButton(text="🔙 Назад", callback_data="bm:home")]


async def _show_home(callback: types.CallbackQuery, prefix: str = ""):
    text, kb = await _home_view()
    await safe_edit_text(callback.message, prefix + text, reply_markup=kb)


async def _categories_kb(prefix: str, show_manager: bool) -> InlineKeyboardMarkup:
    buttons = []
    for code, name, emoji, manager_name in await get_categories_with_share_manager():
        label = f"{emoji} {name}"
        if show_manager:
            label += f" → {manager_name}" if manager_name else " → —"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"{prefix}:{code}")])
    buttons.append(_back_home_row())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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


# ==================== УПРАВЛЯЮЩИЙ КАТЕГОРИИ ====================

@router.callback_query(F.data == "bm:who")
async def brigade_who_categories(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await safe_edit_text(
        callback.message,
        "👤 С какой категории назначить управляющего?\n(справа — кто получает сейчас)",
        reply_markup=await _categories_kb("bm_mc", show_manager=True))
    await callback.answer()


@router.callback_query(F.data.startswith("bm_mc:"))
async def brigade_who_workers(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    cat_code = callback.data.split(":", 1)[1]
    await state.update_data(bm_cat=cat_code)
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"bm_ms:{wid}")]
        for wid, name in await get_all_workers()
    ]
    buttons.append([InlineKeyboardButton(text="🚫 Никто (не начислять)", callback_data="bm_ms:0")])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:who")])
    await safe_edit_text(
        callback.message,
        "👤 Кто получает долю с работ этой категории?\n\n"
        "Уже начисленные записи останутся у прежнего управляющего — "
        "новому пойдёт только то, что запишут после смены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("bm_ms:"))
async def brigade_set_manager(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    cat_code = (await state.get_data()).get("bm_cat")
    if not cat_code:
        await callback.answer("⚠️ Сессия сброшена — выберите категорию заново", show_alert=True)
        return await _show_home(callback)
    wid = int(callback.data.split(":")[1])
    if wid == 0:
        await set_category_share_manager(cat_code, None)
        prefix = "✅ С этой категории больше никто не получает долю.\n\n"
    else:
        worker = await get_worker(wid)
        if not worker:
            return await callback.answer("❌ Работник не найден", show_alert=True)
        await set_category_share_manager(cat_code, wid)
        prefix = f"✅ Управляющий назначен: {worker['name']}\n\n"
    await state.clear()
    await _show_home(callback, prefix)
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
    await safe_edit_text(callback.message, "💵 Выберите категорию:",
                         reply_markup=await _categories_kb("bm_cat", show_manager=False))
    await callback.answer()


@router.callback_query(F.data.startswith("bm_cat:"))
async def brigade_rate_works(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    works = await get_works_for_manager_rate(callback.data.split(":", 1)[1])
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
    await state.update_data(bm_code=code)
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
