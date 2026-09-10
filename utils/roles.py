"""
Роли участников бота.

Роль хранится в БД (workers.role) и кешируется в памяти — фильтры и клавиатуры
должны отвечать мгновенно, без запроса к базе на каждое сообщение.

Владелец (ADMIN_ID из переменных окружения Railway) — всегда админ и единственный,
кто раздаёт роли. Его нельзя понизить даже случайно, поэтому доступ не потеряется.
MANAGER_IDS из окружения тоже остаются управляющими — как страховка на случай,
если что-то не так с базой.
"""

from config import ADMIN_ID, MANAGER_IDS

ROLE_WORKER = 'worker'
ROLE_MANAGER = 'manager'
ROLE_ADMIN = 'admin'

ROLE_TITLES = {
    ROLE_WORKER: '👷 Работник',
    ROLE_MANAGER: '💼 Управляющий',
    ROLE_ADMIN: '🛡 Администратор',
}

ROLE_DESCRIPTIONS = {
    ROLE_WORKER: 'Записывает свою работу, видит свой баланс.',
    ROLE_MANAGER: 'Плюс: авансы, штрафы, отчёты по цеху и сводки.',
    ROLE_ADMIN: 'Полный доступ: расценки, работники, расходы, зарплата.',
}

# кеш из БД
_admins: set = set()
_managers: set = set()


def apply_roles(admins, managers) -> None:
    """Обновляет кеш (вызывается после загрузки из БД и после смены роли)"""
    global _admins, _managers
    _admins = set(admins)
    _managers = set(managers)


def is_owner(user_id: int) -> bool:
    """Владелец бота — из переменных окружения, роль сменить нельзя"""
    return user_id == ADMIN_ID


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID or user_id in _admins


def is_manager(user_id: int) -> bool:
    return user_id in MANAGER_IDS or user_id in _managers


def is_staff(user_id: int) -> bool:
    return is_admin(user_id) or is_manager(user_id)


def role_of(user_id: int) -> str:
    if is_admin(user_id):
        return ROLE_ADMIN
    if is_manager(user_id):
        return ROLE_MANAGER
    return ROLE_WORKER


def role_title(user_id: int) -> str:
    return ROLE_TITLES[role_of(user_id)]
