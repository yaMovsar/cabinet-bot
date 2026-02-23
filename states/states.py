from aiogram.fsm.state import State, StatesGroup


# ==================== РАБОТНИК ====================

class WorkEntry(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()
    choosing_category = State()
    choosing_work = State()
    entering_quantity = State()
    confirming_large = State()


class ViewEntries(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()


class WorkerDeleteEntry(StatesGroup):
    choosing_entry = State()
    confirming = State()


class SupportMessage(StatesGroup):
    entering_message = State()
    waiting_reply = State()


# ==================== АДМИН: ДОБАВЛЕНИЕ ====================

class AdminAddCategory(StatesGroup):
    entering_code = State()
    entering_name = State()
    entering_emoji = State()


class AdminAddWork(StatesGroup):
    choosing_category = State()
    entering_code = State()
    entering_name = State()
    entering_price = State()
    choosing_unit = State()


class AdminAddWorker(StatesGroup):          # ←←← ЭТОГО НЕ ХВАТАЛО! ТЕПЕРЬ ЕСТЬ
    entering_id = State()
    entering_name = State()


# ==================== АДМИН: РАБОТА С РАБОТНИКАМИ ====================

class AdminAssignCategory(StatesGroup):
    choosing_worker = State()
    choosing_category = State()


class AdminRemoveCategory(StatesGroup):
    choosing_worker = State()
    choosing_category = State()


class AdminRenameWorker(StatesGroup):
    choosing_worker = State()
    entering_name = State()


# ==================== АДМИН: РЕДАКТИРОВАНИЕ ====================

class AdminEditPrice(StatesGroup):
    choosing_item = State()
    entering_new_price = State()


class AdminEditCategory(StatesGroup):
    choosing_category = State()
    choosing_action = State()
    entering_new_name = State()
    entering_new_emoji = State()


class AdminEditWork(StatesGroup):
    choosing_work = State()
    choosing_action = State()
    entering_new_name = State()
    choosing_new_category = State()
    choosing_new_unit = State()        # ты уже добавил — оставил


# ==================== АДМИН: УДАЛЕНИЕ ====================

class AdminDeleteCategory(StatesGroup):
    choosing = State()
    confirming = State()


class AdminDeleteWork(StatesGroup):
    choosing = State()
    confirming = State()


class AdminDeleteWorker(StatesGroup):
    choosing = State()
    confirming = State()


class AdminManageEntries(StatesGroup):
    choosing_worker = State()
    viewing_entries = State()
    choosing_action = State()
    entering_new_quantity = State()
    confirming_delete = State()


# ==================== ДЕНЬГИ ====================

class AdminAdvance(StatesGroup):
    choosing_worker = State()
    entering_amount = State()
    entering_comment = State()


class AdminDeleteAdvance(StatesGroup):
    choosing_worker = State()
    choosing_advance = State()
    confirming = State()


class AdminPenalty(StatesGroup):
    choosing_worker = State()
    entering_amount = State()
    entering_reason = State()


class AdminDeletePenalty(StatesGroup):
    choosing_worker = State()
    choosing_penalty = State()
    confirming = State()


# ==================== ОТЧЁТЫ И НАПОМИНАНИЯ ====================

class ReportWorker(StatesGroup):
    choosing_worker = State()


class AdminReminderSettings(StatesGroup):
    main_menu = State()
    entering_time = State()