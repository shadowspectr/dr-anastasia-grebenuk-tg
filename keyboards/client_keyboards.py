from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_supabase import Database
from datetime import datetime, timedelta, date
from aiogram import types
import asyncio
import logging

logger = logging.getLogger(__name__)

def get_client_main_keyboard():
    # Эта функция не обращается к БД, остается синхронной
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записаться на услугу", callback_data="client_book"))
    return builder.as_markup()


async def get_service_categories_keyboard(db: Database):
    builder = InlineKeyboardBuilder()
    # Используем await
    categories = await db.get_service_categories()
    for category in categories:
        builder.add(InlineKeyboardButton(text=category.title, callback_data=f"category_{category.id}"))
    builder.adjust(1)
    return builder.as_markup()


# --- get_services_keyboard ДОЛЖНА БЫТЬ ASYNC И AWAIT'ИТЬ build_keyboard ---
async def get_services_keyboard(db: Database, category_id: str):  # <-- Функция async
    async def get_services():
        return await db.get_services_by_category(category_id)

    async def build_keyboard():
        services = await get_services()
        builder = InlineKeyboardBuilder()
        for service in services:
            builder.add(types.InlineKeyboardButton(
                text=f"{service.title} ({service.price} ₽)",
                callback_data=f"service_{service.id}"
            ))

        builder.add(types.InlineKeyboardButton(
            text="🔙 Назад к категориям",
            callback_data="back_to_category_choice"
        ))
        builder.adjust(1)
        return builder.as_markup()

    # --- ИСПРАВЛЕНИЕ: await build_keyboard() ---
    # Функция get_services_keyboard возвращает markup, а не корутину.
    # Поэтому нужно await'ить build_keyboard.
    return await build_keyboard()  # <-- Здесь был пропущен await
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---


# --- Функция get_date_keyboard ДОЛЖНА БЫТЬ ASYNC ---
async def get_date_keyboard(db: Database):
    builder = InlineKeyboardBuilder()
    today = datetime.now().date()
    
    # Получаем периоды отпуска
    vacation_periods = db.get_vacation_periods() # Предполагаем, что этот метод синхронный

    # --- ЛОГИКА ПОИСКА ПЕРВОГО ДОСТУПНОГО ДНЯ ---
    first_available_date = None
    current_check_date = today + timedelta(days=1) # Начинаем проверку со следующего дня

    while not first_available_date and current_check_date < today + timedelta(days=14): # Ищем в пределах 2 недель, чтобы не зациклиться
        is_available = True
        for period in vacation_periods:
            if period['start_date'] <= current_check_date <= period['end_date']:
                is_available = False
                break
        
        if is_available:
            first_available_date = current_date
            break # Нашли первый доступный день

        current_check_date += timedelta(days=1)
    # --- КОНЕЦ ПОИСКА ПЕРВОГО ДОСТУПНОГО ДНЯ ---

    if not first_available_date:
        # Если за 2 недели не нашли ни одного доступного дня (маловероятно, но возможно)
        logger.warning("No available dates found in the next 14 days.")
        # Можно показать сообщение и кнопку "Вернуться" или "Отменить"
        builder.add(types.InlineKeyboardButton(text="Нет доступных дат", callback_data="no_dates_available"))
        builder.add(types.InlineKeyboardButton(text="🔙 Назад к услугам", callback_data="back_to_service_choice"))
        builder.adjust(1)
        return builder.as_markup()

    # --- Отображаем 7 дней, начиная с первого доступного ---
    for i in range(7): # Показываем 7 дней
        current_date = first_available_date + timedelta(days=i)
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Проверяем, не попадает ли current_date в период отпуска
        is_available = True
        for period in vacation_periods:
            if period['start_date'] <= current_date <= period['end_date']:
                is_available = False
                break

        if is_available:
            builder.add(types.InlineKeyboardButton(
                text=f"{current_date.strftime('%d.%m')} ({current_date.strftime('%a')})",
                callback_data=f"date_{date_str}"
            ))
        # Если день в отпуске, мы его просто пропускаем, не добавляя кнопку

    # Кнопка "Назад" для выбора услуги
    builder.add(types.InlineKeyboardButton(
        text="🔙 Назад к услугам",
        callback_data="back_to_service_choice"
    ))
    builder.adjust(3) # Например, 3 кнопки в ряду
    return builder.as_markup()



# --- Функция get_time_slots_keyboard ---
# Она уже должна быть async, так как использует db.get_appointments_for_day
async def get_time_slots_keyboard(target_date: datetime, db: Database):
    builder = InlineKeyboardBuilder()

    try:
        # --- ВАЖНО: db.get_appointments_for_day - ASYNC МЕТОД ---
        appointments_on_day = await db.get_appointments_for_day(target_date)
        booked_times = {app.appointment_time.strftime('%H:%M') for app in appointments_on_day if app.appointment_time}
    except Exception as e:
        logger.error(f"Error fetching appointments for time slot check on {target_date.date()}: {e}")
        booked_times = set()

    start_hour = 9
    end_hour = 18
    slot_interval_minutes = 60

    current_time = target_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)

    while current_time.hour < end_hour:
        slot_time_str = current_time.strftime('%H:%M')

        if slot_time_str not in booked_times:
            builder.add(types.InlineKeyboardButton(
                text=slot_time_str,
                callback_data=f"time_{slot_time_str}"
            ))
        else:
            pass  # Не добавляем занятые слоты

        current_time += timedelta(minutes=slot_interval_minutes)

    builder.add(types.InlineKeyboardButton(
        text="🔙 Назад к выбору дня",
        callback_data="back_to_date_choice"
    ))
    builder.adjust(3)
    return builder.as_markup()


def get_confirmation_keyboard():
    # Эта функция не обращается к БД, остается синхронной
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="confirm_booking"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_booking"))
    return builder.as_markup()