import os
import logging
from datetime import date

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile

from database import (
    get_all_workers, get_worker_full_stats, get_worker_monthly_details,
    get_worker_categories
)
from states import ManagerWorkerReport, ManagerShopReport
from utils import send_long_message, MONTHS_RU, format_salary_block, format_work_summary
from handlers.filters import StaffFilter
from reports import generate_worker_report, generate_salary_report

router = Router()


def _month_kb(prefix: str) -> InlineKeyboardMarkup:
    today = date.today()
    buttons = []
    for i in range(4):
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        label = f"📅 {MONTHS_RU[m]} {y}" + (" (текущий)" if i == 0 else "")
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"{prefix}:{y}:{m}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="mgr_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== ОТЧЁТ ПО СОТРУДНИКУ ====================

@router.message(F.text == "👤 Отчёт по сотрудникам", StaffFilter())
async def manager_worker_report_start(message: types.Message, state: FSMContext):
    await state.clear()
    workers = await get_all_workers()
    if not workers:
        await message.answer("📭 Нет работников.")
        return
    buttons = [
        [InlineKeyboardButton(text=f"👤 {name}", callback_data=f"mgr_wr_w:{tid}")]
        for tid, name in workers
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="mgr_cancel")])
    await message.answer("👤 Выберите сотрудника:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(ManagerWorkerReport.choosing_worker)


@router.callback_query(F.data.startswith("mgr_wr_w:"), ManagerWorkerReport.choosing_worker)
async def manager_worker_chosen(callback: types.CallbackQuery, state: FSMContext):
    wid = int(callback.data.split(":")[1])
    workers = await get_all_workers()
    wname = next((n for t, n in workers if t == wid), "?")
    await state.update_data(worker_id=wid, worker_name=wname)
    await callback.message.edit_text(
        f"👤 {wname}\n\nВыберите месяц:",
        reply_markup=_month_kb("mgr_wr_m")
    )
    await state.set_state(ManagerWorkerReport.choosing_month)
    await callback.answer()


@router.callback_query(F.data.startswith("mgr_wr_m:"), ManagerWorkerReport.choosing_month)
async def manager_worker_month_chosen(callback: types.CallbackQuery, state: FSMContext):
    _, year, month = callback.data.split(":")
    year, month = int(year), int(month)
    data = await state.get_data()
    await state.update_data(year=year, month=month)
    await callback.message.edit_text(
        f"👤 {data['worker_name']} — {MONTHS_RU[month]} {year}\n\nФормат отчёта:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Текстом в чат", callback_data="mgr_wr_fmt:text")],
            [InlineKeyboardButton(text="📊 Excel файл", callback_data="mgr_wr_fmt:excel")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="mgr_cancel")],
        ])
    )
    await state.set_state(ManagerWorkerReport.choosing_format)
    await callback.answer()


@router.callback_query(F.data.startswith("mgr_wr_fmt:"), ManagerWorkerReport.choosing_format)
async def manager_worker_report_format(callback: types.CallbackQuery, state: FSMContext):
    fmt = callback.data.split(":")[1]
    data = await state.get_data()
    wid, wname, year, month = data["worker_id"], data["worker_name"], data["year"], data["month"]

    await callback.message.edit_text("⏳ Формирую отчёт...")

    if fmt == "excel":
        try:
            fn = await generate_worker_report(wid, wname, year, month)
            await callback.message.answer_document(
                FSInputFile(fn, filename=f"otchet_{wname}_{MONTHS_RU[month]}_{year}.xlsx"),
                caption=f"📊 {wname} — {MONTHS_RU[month]} {year}"
            )
            os.remove(fn)
        except Exception as e:
            logging.exception(e)
            await callback.message.answer(f"❌ Ошибка: {e}")
    else:
        details = await get_worker_monthly_details(wid, year, month)
        stats = await get_worker_full_stats(wid, year, month)
        cats = await get_worker_categories(wid)
        ce = "".join([c[2] for c in cats]) if cats else ""

        if not details:
            await callback.message.answer(
                f"📭 {ce}{wname} — нет записей за {MONTHS_RU[month]} {year}"
            )
            await state.clear()
            await callback.answer()
            return

        text = f"📊 {ce}{wname}\n📅 {MONTHS_RU[month]} {year}\n\n"
        current_cat = ""
        cat_total = 0
        for pl_name, c_emoji, c_name, qty, price, total, price_type in details:
            if c_name != current_cat:
                if current_cat:
                    text += f"   📊 Итого: {int(cat_total)} руб\n\n"
                current_cat = c_name
                cat_total = 0
                text += f"{c_emoji} {c_name}:\n"
            unit = "м²" if price_type == "square" else "шт"
            qty_display = f"{qty:.2f}" if price_type == "square" else str(int(qty))
            text += f"   ▪️ {pl_name}: {qty_display} {unit} × {int(price)} = {int(total)} руб\n"
            cat_total += total
        if current_cat:
            text += f"   📊 Итого: {int(cat_total)} руб\n"

        text += f"\n━━━━━━━━━━━━━━━━━━━\n"
        text += format_salary_block(stats)
        if stats['work_days'] > 0:
            text += f"\n📈 Среднее в день: {int(stats['earned'] / stats['work_days']):,} руб"

        await send_long_message(callback.message, text)

    await state.clear()
    await callback.answer()


# ==================== ОТЧЁТ ПО ЦЕХУ ====================

@router.message(F.text == "🏭 Отчёт по цеху", StaffFilter())
async def manager_shop_report_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🏭 Отчёт по цеху\n\nВыберите месяц:", reply_markup=_month_kb("mgr_sh_m"))
    await state.set_state(ManagerShopReport.choosing_month)


@router.callback_query(F.data.startswith("mgr_sh_m:"), ManagerShopReport.choosing_month)
async def manager_shop_month_chosen(callback: types.CallbackQuery, state: FSMContext):
    _, year, month = callback.data.split(":")
    year, month = int(year), int(month)
    await state.update_data(year=year, month=month)
    await callback.message.edit_text(
        f"🏭 Цех — {MONTHS_RU[month]} {year}\n\nФормат отчёта:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Текстом в чат", callback_data="mgr_sh_fmt:text")],
            [InlineKeyboardButton(text="📊 Excel файл", callback_data="mgr_sh_fmt:excel")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="mgr_cancel")],
        ])
    )
    await state.set_state(ManagerShopReport.choosing_format)
    await callback.answer()


@router.callback_query(F.data.startswith("mgr_sh_fmt:"), ManagerShopReport.choosing_format)
async def manager_shop_report_format(callback: types.CallbackQuery, state: FSMContext):
    fmt = callback.data.split(":")[1]
    data = await state.get_data()
    year, month = data["year"], data["month"]

    await callback.message.edit_text("⏳ Формирую отчёт по цеху...")

    workers = await get_all_workers()

    if fmt == "excel":
        try:
            workers_data = []
            for tid, name in workers:
                stats = await get_worker_full_stats(tid, year, month)
                if round(stats['balance'], 2) == 0:
                    continue
                details = await get_worker_monthly_details(tid, year, month)
                workers_data.append({
                    'name': name,
                    'work_summary': format_work_summary(details),
                    'earned': stats['earned'],
                    'fixed_salary': stats['fixed_salary'],
                    'bonus': stats['bonus'],
                    'advances': stats['advances'],
                    'penalties': stats['penalties'],
                    'balance': stats['balance'],
                })
            if not workers_data:
                await callback.message.answer(f"📭 Нет данных за {MONTHS_RU[month]} {year}.")
                await state.clear()
                await callback.answer()
                return
            workers_data.sort(key=lambda x: x['balance'], reverse=True)
            fn = await generate_salary_report(year, month, workers_data)
            total_pay = sum(w['balance'] for w in workers_data)
            await callback.message.answer_document(
                FSInputFile(fn, filename=f"cex_{MONTHS_RU[month]}_{year}.xlsx"),
                caption=(
                    f"🏭 Отчёт по цеху\n"
                    f"📅 {MONTHS_RU[month]} {year}\n\n"
                    f"👥 Работников: {len(workers_data)}\n"
                    f"💼 Итого к выплате: {int(total_pay):,} руб"
                )
            )
            os.remove(fn)
        except Exception as e:
            logging.exception(e)
            await callback.message.answer(f"❌ Ошибка: {e}")
    else:
        text = f"🏭 Отчёт по цеху — {MONTHS_RU[month]} {year}\n"
        text += "━━━━━━━━━━━━━━━━━━━\n\n"
        grand_earned = grand_salary = grand_bonus = grand_adv = grand_pen = grand_pay = 0
        has_data = False

        for tid, name in workers:
            stats = await get_worker_full_stats(tid, year, month)
            if stats['earned'] <= 0 and stats['fixed_salary'] <= 0 and stats['advances'] <= 0 and stats['penalties'] <= 0:
                continue
            has_data = True
            cats = await get_worker_categories(tid)
            ce = "".join([c[2] for c in cats]) if cats else ""
            icon = "💰" if stats['balance'] > 0 else "✅"
            text += f"{icon} {ce}{name}\n"
            for line in format_salary_block(stats).splitlines():
                text += f"   {line}\n"
            text += "\n"
            grand_earned += stats['earned']
            grand_salary += stats['fixed_salary']
            grand_bonus += stats['bonus']
            grand_adv += stats['advances']
            grand_pen += stats['penalties']
            grand_pay += stats['balance']

        if not has_data:
            await callback.message.answer(f"📭 Нет данных за {MONTHS_RU[month]} {year}.")
            await state.clear()
            await callback.answer()
            return

        text += "━━━━━━━━━━━━━━━━━━━\n"
        text += f"💰 Фонд (сдельно): {int(grand_earned)} руб\n"
        if grand_salary > 0:
            text += f"🏢 Оклады: {int(grand_salary)} руб\n"
        if grand_bonus > 0:
            text += f"🏆 Премии: {int(grand_bonus)} руб\n"
        if grand_adv > 0:
            text += f"💳 Авансы: {int(grand_adv)} руб\n"
        if grand_pen > 0:
            text += f"⚠️ Штрафы: {int(grand_pen)} руб\n"
        text += f"💼 Итого к выплате: {int(grand_pay):,} руб"

        await send_long_message(callback.message, text)

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "mgr_cancel")
async def manager_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()
