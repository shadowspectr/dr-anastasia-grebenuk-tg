# keyboards/client_keyboards.py

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_supabase import Database
# Добавляем timedelta в эту строку
from datetime import datetime, time, timedelta
from typing import List
import pytz

# Указываем наш целевой часовой пояс
TIMEZONE = pytz.timezone('Europe/Moscow')


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


# --- Новая логика клавиатур с часовыми поясами ---

def get_upcoming_dates_keyboard():
    builder = InlineKeyboardBuilder()
    # Получаем текущее время в нашем часовом поясе
    today = datetime.now(TIMEZONE)
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    for i in range(1, 8):
        # Теперь timedelta будет работать
        day = today + timedelta(days=i)
        day_str = day.strftime('%d.%m')
        weekday_str = weekdays[day.weekday()]
        builder.add(InlineKeyboardButton(
            text=f"{day_str} ({weekday_str})",
            callback_data=f"date_{day.strftime('%Y-%m-%d')}"
        ))
    builder.adjust(3)
    return builder.as_markup()


def get_time_slots_keyboard(target_date: datetime, busy_slots: List[datetime]):
    builder = InlineKeyboardBuilder()

    busy_hours = {slot.astimezone(TIMEZONE).time().hour for slot in busy_slots}

    time_slots = []
    # Генерируем слоты с 9:00 до 19:00
    for hour in range(9, 20):
        slot_time = time(hour, 0)

        # Создаем "осознающий" объект времени для сравнения
        slot_datetime = TIMEZONE.localize(target_date.replace(hour=hour, minute=0))

        # Пропускаем прошедшее время
        if slot_datetime <= datetime.now(TIMEZONE):
            continue

        # Если час не занят, предлагаем его
        if hour not in busy_hours:
            time_slots.append(slot_time)

    if not time_slots:
        builder.add(InlineKeyboardButton(text="❌ На эту дату нет свободного времени", callback_data="no_slots"))
    else:
        for time_slot in time_slots:
            builder.add(InlineKeyboardButton(text=time_slot.strftime("%H:%M"),
                                             callback_data=f"time_{time_slot.strftime('%H:%M')}"))

    builder.add(InlineKeyboardButton(text="🔙 Назад к выбору даты", callback_data="back_to_date_choice"))
    builder.adjust(4)
    return builder.as_markup()


def get_confirmation_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="confirm_booking"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_booking"))
    return builder.as_markup()