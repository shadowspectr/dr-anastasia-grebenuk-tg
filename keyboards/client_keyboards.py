# keyboards/client_keyboards.py

from aiogram.types import InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_supabase import Database
from datetime import datetime, timedelta, date
from typing import List

# Импорты для календаря
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback


# --- Клавиатуры для основного меню и услуг ---

def get_client_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записаться на услугу", callback_data="client_book"))
    return builder.as_markup()


async def get_service_categories_keyboard(db: Database):
    builder = InlineKeyboardBuilder()
    categories = await db.get_service_categories()
    for category in categories:
        builder.add(InlineKeyboardButton(text=category.title, callback_data=f"category_{category.id}"))
    builder.adjust(1)
    return builder.as_markup()


async def get_services_keyboard(db: Database, category_id: str):
    builder = InlineKeyboardBuilder()
    services = await db.get_services_by_category(category_id)
    for service in services:
        builder.add(
            InlineKeyboardButton(text=f"{service.title} ({service.price} ₽)", callback_data=f"service_{service.id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="client_book"))
    builder.adjust(1)
    return builder.as_markup()


# --- ИСПРАВЛЕННАЯ ФУНКЦИЯ КАЛЕНДАРЯ ---

async def get_calendar_keyboard():
    """
    Создает инлайн-календарь для выбора даты.
    """
    # В новой версии конструктор принимает только show_alerts
    simple_calendar = SimpleCalendar(show_alerts=True)

    # Локаль передается в метод start_calendar
    return simple_calendar.start_calendar(locale='ru_RU')


def get_time_slots_keyboard(target_date: datetime, busy_slots: List[datetime]):
    """
    Генерирует клавиатуру со свободными временными слотами.
    """
    builder = InlineKeyboardBuilder()
    busy_times = [slot.astimezone().time() for slot in busy_slots]

    time_slots = []
    for hour in range(9, 19):
        for minute in [0, 30]:
            current_slot_time = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()

            # Проверяем, что дата не в прошлом
            # И что время еще не прошло для сегодняшнего дня
            now = datetime.now()
            if target_date.date() < now.date() or \
                    (target_date.date() == now.date() and current_slot_time <= now.time()):
                continue

            if current_slot_time not in busy_times:
                time_slots.append(current_slot_time)

    if not time_slots:
        builder.add(InlineKeyboardButton(text="❌ На эту дату нет свободного времени", callback_data="no_slots"))
    else:
        for time_slot in time_slots:
            builder.add(InlineKeyboardButton(text=time_slot.strftime("%H:%M"),
                                             callback_data=f"time_{time_slot.strftime('%H:%M')}"))

    builder.add(InlineKeyboardButton(text="🔙 Назад к выбору даты", callback_data="back_to_calendar"))
    builder.adjust(4)
    return builder.as_markup()


def get_confirmation_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="confirm_booking"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_booking"))
    return builder.as_markup()