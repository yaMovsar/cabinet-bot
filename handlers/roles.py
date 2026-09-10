import logging

from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_TOKEN
from database import (
    get_workers_with_roles, set_worker_role, get_worker_role, load_role_sets
)
from states import AdminRoles
from keyboards import get_main_keyboard
from utils import (
    apply_roles, is_owner,
    ROLE_WORKER, ROLE_MANAGER, ROLE_ADMIN, ROLE_TITLES, ROLE_DESCRIPTIONS,
)
from handlers.filters import OwnerFilter

router = Router()
bot = Bot(token=BOT_TOKEN)


async def refresh_role_cache():
    admins, managers = await load_role_sets()
    apply_roles(admins, managers)


async def _render_roles(target, state: FSMContext, edit=False):
    """Список участников с их ролями"""
    workers = await get_workers_with_roles()

    text = "👥 <b>Роли участников</b>\n\n"
    if not workers:
        text += "Пока никто не запускал бота."
    else:
        text += "Нажмите на человека, чтобы изменить роль.\n\n"
        for _tid, name, role in workers:
            text += f"{ROLE_TITLES[role].split()[0]} {name} — {ROLE_TITLES[role].split(maxsplit=1)[1]}\n"

    text += (
        "\n<i>Управляющий может выдавать авансы, выписывать штрафы "
        "и смотреть отчёты по цеху.</i>"
    )

    buttons = []
    for tid, name, role in workers:
        icon = ROLE_TITLES[role].split()[0]
        suffix = " (вы)" if is_owner(tid) else ""
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {name}{suffix}",
            callback_data=f"role_user:{tid}"
        )])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="role_close")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(AdminRoles.viewing)


@router.message(F.text == "👥 Роли", OwnerFilter())
async def roles_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await _render_roles(message, state)


@router.callback_query(F.data == "role_close", AdminRoles.viewing)
async def roles_close(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Ок")
    await callback.answer()


@router.callback_query(F.data == "role_back", AdminRoles.viewing)
async def roles_back(callback: types.CallbackQuery, state: FSMContext):
    await _render_roles(callback.message, state, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("role_user:"), AdminRoles.viewing)
async def role_user_chosen(callback: types.CallbackQuery, state: FSMContext):
    tid = int(callback.data.split(":")[1])

    if is_owner(tid):
        await callback.answer(
            "🛡 Это вы — владелец бота. Свою роль изменить нельзя, "
            "иначе можно потерять доступ.",
            show_alert=True
        )
        return

    workers = await get_workers_with_roles()
    person = next(((t, n, r) for t, n, r in workers if t == tid), None)
    if not person:
        await callback.answer("❌ Человек не найден", show_alert=True)
        return

    _tid, name, role = person
    await state.update_data(target_id=tid, target_name=name)

    text = f"👤 <b>{name}</b>\n\nСейчас: {ROLE_TITLES[role]}\n\nВыберите новую роль:"
    buttons = []
    for r in (ROLE_WORKER, ROLE_MANAGER, ROLE_ADMIN):
        mark = "✅ " if r == role else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{ROLE_TITLES[r]}",
            callback_data=f"role_set:{r}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="role_back")])

    for r in (ROLE_WORKER, ROLE_MANAGER, ROLE_ADMIN):
        text += f"\n\n{ROLE_TITLES[r]}\n<i>{ROLE_DESCRIPTIONS[r]}</i>"

    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("role_set:"), AdminRoles.viewing)
async def role_set(callback: types.CallbackQuery, state: FSMContext):
    new_role = callback.data.split(":")[1]
    if new_role not in (ROLE_WORKER, ROLE_MANAGER, ROLE_ADMIN):
        await callback.answer("❌ Неизвестная роль", show_alert=True)
        return

    data = await state.get_data()
    tid = data.get("target_id")
    name = data.get("target_name", "работник")
    if not tid:
        await callback.answer("❌ Не выбран человек", show_alert=True)
        await _render_roles(callback.message, state, edit=True)
        return

    if is_owner(tid):
        await callback.answer("🛡 Роль владельца изменить нельзя", show_alert=True)
        return

    old_role = await get_worker_role(tid)
    if old_role == new_role:
        await callback.answer("Эта роль уже стоит")
        await _render_roles(callback.message, state, edit=True)
        return

    await set_worker_role(tid, new_role)
    await refresh_role_cache()

    await callback.answer(f"✅ {name}: {ROLE_TITLES[new_role]}")

    # человеку — уведомление и сразу новая клавиатура
    try:
        if new_role == ROLE_WORKER:
            note = (
                "ℹ️ Ваша роль изменена: 👷 Работник\n\n"
                "Доступ к деньгам и отчётам по цеху закрыт."
            )
        else:
            note = (
                f"🎉 Вам выдана роль: {ROLE_TITLES[new_role]}\n\n"
                f"{ROLE_DESCRIPTIONS[new_role]}\n\n"
                f"Новые кнопки уже в меню внизу."
            )
        await bot.send_message(tid, note, reply_markup=get_main_keyboard(tid))
    except Exception as e:
        logging.warning(f"Не смог уведомить {name} ({tid}) о смене роли: {e}")

    await _render_roles(callback.message, state, edit=True)
