from aiogram.filters import Filter
from aiogram import types
from config import ADMIN_ID, MANAGER_IDS


class AdminFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id == ADMIN_ID


class StaffFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id == ADMIN_ID or message.from_user.id in MANAGER_IDS