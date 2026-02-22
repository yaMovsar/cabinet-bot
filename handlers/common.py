from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID, MANAGER_IDS
from database import add_worker, worker_exists
from keyboards import (
    get_main_keyboard, get_admin_keyboard, get_manager_keyboard,
    get_add_keyboard, get_edit_keyboard, get_delete_keyboard,
    get_info_keyboard, get_money_keyboard
)
from handlers.filters import AdminFilter, StaffFilter

router = Router()


@router.message(Command("start"))
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


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено.",
                         reply_markup=get_main_keyboard(message.from_user.id))


@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


# ==================== НАВИГАЦИЯ ====================

@router.message(F.text == "👑 Админ-панель")
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


@router.message(F.text == "📊 Панель отчётов")
async def manager_panel(message: types.Message, state: FSMContext, is_manager: bool, **kwargs):
    if not is_manager:
        await message.answer("⛔ Нет доступа.")
        return
    await state.clear()
    await message.answer("📊 Панель отчётов", reply_markup=get_manager_keyboard())


@router.message(F.text == "➕ Добавить", AdminFilter())
async def menu_add(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("➕ Добавить:", reply_markup=get_add_keyboard())


@router.message(F.text == "✏️ Редактировать", AdminFilter())
async def menu_edit(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("✏️ Редактировать:", reply_markup=get_edit_keyboard())


@router.message(F.text == "🗑 Удалить", AdminFilter())
async def menu_delete(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🗑 Удалить:", reply_markup=get_delete_keyboard())


@router.message(F.text == "📂 Справочники", StaffFilter())
async def menu_info(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📂 Справочники:", reply_markup=get_info_keyboard())


@router.message(F.text == "💰 Деньги", StaffFilter())
async def menu_money(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "💰 Раздел Деньги\n\n💳 — Авансы\n⚠️ — Штрафы\n💰 — Баланс\n📊 — Заработок\n🏆 — Рейтинг",
        reply_markup=get_money_keyboard()
    )


@router.message(F.text == "🔙 В админ-панель")
async def back_to_admin(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Админ-панель", reply_markup=get_admin_keyboard())
    elif message.from_user.id in MANAGER_IDS:
        await message.answer("📊 Панель отчётов", reply_markup=get_manager_keyboard())


@router.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню",
                         reply_markup=get_main_keyboard(message.from_user.id))