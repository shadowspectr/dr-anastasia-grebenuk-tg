# keyboards/admin_keyboards.py

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_admin_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записи на сегодня", callback_data="admin_today"))
    # --- ДОБАВЛЯЕМ НОВУЮ КНОПКУ ---
    builder.row(InlineKeyboardButton(text="✍️ Новая запись", callback_data="admin_new_appointment"))
    return builder.as_markup()

# Принимаем строковый google_event_id
def get_admin_appointment_actions_keyboard(google_event_id: str):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🗑 Удалить/Отменить запись", callback_data=f"admin_delete_{google_event_id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_today"))
    builder.adjust(1)
    return builder.as_markup()