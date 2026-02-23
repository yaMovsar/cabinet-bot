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


# ==================== АДМИН: ДОБАВЛЕНИЕ ====================

class AdminAddCategory(StatesGroup):
    entering_code = State()
    entering_name = State()
    entering_emoji = State()


class AdminAddWork(StatesGroup):
    choosing_category = State()
    entering_code = State()
    entering_name = State()
    choosing_price_type = State()  # ← НОВОЕ
    entering_price = State()


class AdminAddWorker(StatesGroup):
    entering_id = State()
    entering_name = State()


# ==================== АДМИН: РЕДАКТИРОВАНИЕ ====================

class AdminAssignCategory(StatesGroup):
    choosing_worker = State()
    choosing_category = State()


class AdminRemoveCategory(StatesGroup):
    choosing_worker = State()
    choosing_category = State()


class AdminEditPrice(StatesGroup):
    choosing_item = State()
    entering_new_price = State()


class AdminRenameWorker(StatesGroup):
    choosing_worker = State()
    entering_name = State()


class AdminManageEntries(StatesGroup):
    choosing_worker = State()
    viewing_entries = State()
    choosing_action = State()
    entering_new_quantity = State()
    confirming_delete = State()


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


# ==================== ОТЧЁТЫ ====================

class ReportWorker(StatesGroup):
    choosing_worker = State()


# ==================== НАПОМИНАНИЯ ====================

class AdminReminderSettings(StatesGroup):
    main_menu = State()
    entering_time = State()