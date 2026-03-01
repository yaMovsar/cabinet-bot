from .states import (
    WorkEntry, ViewEntries, WorkerDeleteEntry, WorkerEditEntry,
    AdminAddCategory, AdminAddWork, AdminAddWorker,
    AdminAssignCategory, AdminRemoveCategory,
    AdminEditPrice, AdminRenameWorker, AdminManageEntries,
    AdminEditCategory, AdminEditWork,
    AdminDeleteCategory, AdminDeleteWork, AdminDeleteWorker,
    AdminAdvance, AdminDeleteAdvance, AdminPenalty, AdminDeletePenalty,
    ReportWorker, MonthlySummaryWorker,
    AdminReminderSettings,
    MonthlyTotals  # ← ДОБАВЛЕНО
)

__all__ = [
    'WorkEntry', 'ViewEntries', 'WorkerDeleteEntry', 'WorkerEditEntry',
    'AdminAddCategory', 'AdminAddWork', 'AdminAddWorker',
    'AdminAssignCategory', 'AdminRemoveCategory',
    'AdminEditPrice', 'AdminRenameWorker', 'AdminManageEntries',
    'AdminEditCategory', 'AdminEditWork',
    'AdminDeleteCategory', 'AdminDeleteWork', 'AdminDeleteWorker',
    'AdminAdvance', 'AdminDeleteAdvance', 'AdminPenalty', 'AdminDeletePenalty',
    'ReportWorker', 'MonthlySummaryWorker',
    'AdminReminderSettings',
    'MonthlyTotals'  # ← ДОБАВЛЕНО
]