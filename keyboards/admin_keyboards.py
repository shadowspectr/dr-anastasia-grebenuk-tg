from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_admin_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записи на сегодня", callback_data="admin_today"))
    # Можно добавить другие кнопки
    return builder.as_markup()

def get_admin_appointment_actions_keyboard(appointment_id: str):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Завершить", callback_data=f"admin_complete_{appointment_id}"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data=f"admin_cancel_{appointment_id}"))
    builder.add(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_{appointment_id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_today"))
    builder.adjust(2)
    return builder.as_markup()