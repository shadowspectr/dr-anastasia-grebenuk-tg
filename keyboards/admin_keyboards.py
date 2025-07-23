# keyboards/admin_keyboards.py

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_admin_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записи на сегодня", callback_data="admin_today"))
    builder.add(types.InlineKeyboardButton(text="➕ Записать клиента", callback_data="admin_book_client"))
    builder.adjust(1)
    return builder.as_markup()

# Принимаем строковый app_id (UUID)
def get_admin_appointment_actions_keyboard(app_id: str):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Завершить", callback_data=f"admin_complete_{app_id}"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data=f"admin_cancel_{app_id}"))
    builder.add(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{app_id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_today"))
    builder.adjust(2)
    return builder.as_markup()