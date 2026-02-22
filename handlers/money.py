import logging
from datetime import date

from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_ID, BOT_TOKEN
from database import (
    get_all_workers, get_worker_full_stats,
    add_advance, get_worker_advances, get_worker_advances_total, delete_advance,
    add_penalty, get_worker_penalties, get_worker_penalties_total, delete_penalty,
    get_all_workers_balance, get_monthly_total, get_worker_monthly_details,
    get_worker_categories
)
from states import AdminAdvance, AdminDeleteAdvance, AdminPenalty, AdminDeletePenalty
from keyboards import get_money_keyboard
from utils import format_date, format_date_short, send_long_message, MONTHS_RU
from handlers.filters import StaffFilter

router = Router()
bot = Bot(token=BOT_TOKEN)


# ==================== АВАНСЫ ====================

@router.message(F.text == "💳 Выдать аванс", StaffFilter())
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


@router.callback_query(F.data.startswith("adv_w:"), AdminAdvance.choosing_worker)
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


@router.message(AdminAdvance.entering_amount)
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


@router.message(AdminAdvance.entering_comment)
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

    try:
        notify = f"💳 Вам выдан аванс: {int(data['amount'])} руб"
        if comment:
            notify += f"\n💬 {comment}"
        notify += f"\n📊 Остаток к выплате: {int(stats['balance'])} руб"
        await bot.send_message(data["worker_id"], notify)
    except Exception as e:
        logging.error(f"Notify worker advance: {e}")

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


@router.message(F.text == "💳 Удалить аванс", StaffFilter())
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


@router.callback_query(F.data.startswith("dadv_w:"), AdminDeleteAdvance.choosing_worker)
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


@router.callback_query(F.data.startswith("dadv_a:"), AdminDeleteAdvance.choosing_advance)
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


@router.callback_query(F.data.startswith("dadv_c:"), AdminDeleteAdvance.confirming)
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

@router.message(F.text == "⚠️ Выписать штраф", StaffFilter())
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


@router.callback_query(F.data.startswith("pen_w:"), AdminPenalty.choosing_worker)
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


@router.message(AdminPenalty.entering_amount)
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


@router.message(AdminPenalty.entering_reason)
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

    try:
        notify = f"⚠️ Вам выписан штраф: {int(data['amount'])} руб"
        if reason:
            notify += f"\n📝 Причина: {reason}"
        notify += f"\n📊 Остаток к выплате: {int(stats['balance'])} руб"
        await bot.send_message(data["worker_id"], notify)
    except Exception as e:
        logging.error(f"Notify worker penalty: {e}")

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


@router.message(F.text == "⚠️ Удалить штраф", StaffFilter())
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


@router.callback_query(F.data.startswith("dpen_w:"), AdminDeletePenalty.choosing_worker)
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


@router.callback_query(F.data.startswith("dpen_p:"), AdminDeletePenalty.choosing_penalty)
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


@router.callback_query(F.data.startswith("dpen_c:"), AdminDeletePenalty.confirming)
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

@router.message(F.text == "💰 Баланс работников", StaffFilter())
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

@router.message(F.text == "📊 Заработок за месяц", StaffFilter())
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

@router.message(F.text == "🏆 Рейтинг работников", StaffFilter())
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

@router.message(F.text == "💼 Итоги месяца", StaffFilter())
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