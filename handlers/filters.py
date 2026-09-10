from aiogram.filters import Filter
from aiogram import types
from utils.roles import is_admin, is_staff, is_owner


class AdminFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return is_admin(message.from_user.id)


class StaffFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return is_staff(message.from_user.id)


class OwnerFilter(Filter):
    """Только владелец бота — раздача ролей"""
    async def __call__(self, message: types.Message) -> bool:
        return is_owner(message.from_user.id)