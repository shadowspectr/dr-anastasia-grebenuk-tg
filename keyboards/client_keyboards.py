# keyboards/client_keyboards.py

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_supabase import Database
from datetime import datetime, timedelta, time
from typing import List


# --- Клавиатуры для основного меню и услуг (без изменений) ---

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


# --- НОВАЯ ЛОГИКА КЛАВИАТУР ДЛЯ ДАТЫ И ВРЕМЕНИ ---

def get_upcoming_dates_keyboard():
    """
    Создает клавиатуру с кнопками на ближайшие 7 дней (не считая сегодня).
    """
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    # Названия дней недели на русском
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    for i in range(1, 8):  # От 1 до 7, чтобы начать с завтрашнего дня
        day = today + timedelta(days=i)
        day_str = day.strftime('%d.%m')
        weekday_str = weekdays[day.weekday()]

        builder.add(InlineKeyboardButton(
            text=f"{day_str} ({weekday_str})",
            callback_data=f"date_{day.strftime('%Y-%m-%d')}"
        ))

    builder.adjust(3)  # По 3 кнопки в ряд
    return builder.as_markup()


def get_time_slots_keyboard(target_date: datetime, busy_slots: List[datetime]):
    """
    Генерирует клавиатуру со свободными слотами с шагом в 2 часа.
    Учитывает, что каждый прием длится 2 часа.
    """
    builder = InlineKeyboardBuilder()

    # --- Логика определения занятых интервалов ---
    # Создаем множество всех часов, которые заняты.
    # Если запись в 10:00, то заняты часы 10 и 11.
    busy_hours = set()
    for slot in busy_slots:
        slot_time = slot.astimezone().time()
        busy_hours.add(slot_time.hour)
        busy_hours.add(slot_time.hour + 1)  # Следующий час тоже занят

    time_slots = []
    # Генерируем возможные слоты с 9:00 до 17:00 (чтобы последняя запись в 17:00 закончилась в 19:00)
    for hour in range(9, 18, 2):  # Шаг 2 часа: 9, 11, 13, 15, 17
        slot_time = time(hour, 0)

        # Проверяем, что слот еще не прошел для сегодняшнего дня
        if target_date.date() == datetime.now().date() and slot_time <= datetime.now().time():
            continue

        # Проверяем, что ни текущий час, ни следующий не заняты
        if hour not in busy_hours and (hour + 1) not in busy_hours:
            time_slots.append(slot_time)

    if not time_slots:
        builder.add(InlineKeyboardButton(text="❌ На эту дату нет свободного времени", callback_data="no_slots"))
    else:
        for time_slot in time_slots:
            builder.add(InlineKeyboardButton(text=time_slot.strftime("%H:%M"),
                                             callback_data=f"time_{time_slot.strftime('%H:%M')}"))

    builder.add(InlineKeyboardButton(text="🔙 Назад к выбору даты", callback_data="back_to_date_choice"))
    builder.adjust(3)  # По 3 кнопки в ряд
    return builder.as_markup()


def get_confirmation_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="confirm_booking"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_booking"))
    return builder.as_markup()