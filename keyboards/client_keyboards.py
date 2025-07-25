from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_supabase import Database
from datetime import datetime, timedelta
from aiogram import types


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

    available_weekdays = {1, 3, 4}  # Tuesday, Thursday, Friday

    days_added = 0

    # Список для дней недели на русском
    # Понедельник - 0, Вторник - 1, ..., Воскресенье - 6
    days_of_week_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    for i in range(1, 15):
        current_date = today + timedelta(days=i)

        if current_date.weekday() in available_weekdays:
            date_str = current_date.strftime('%Y-%m-%d')

            # --- ИСПРАВЛЕНИЕ: Форматирование даты с русским днем недели ---
            day_name_ru = days_of_week_ru[current_date.weekday()]  # Получаем сокращенное название дня

            button_text = f"{current_date.strftime('%d.%m')} ({day_name_ru})"
            # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

            builder.add(types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"date_{date_str}"
            ))
            days_added += 1
            # Перенос на новую строку каждые 3 кнопки
            if days_added % 3 == 0:
                builder.adjust(3)

    # Если последний ряд не полный, adjust(3) может работать некорректно.
    # Лучше использовать adjust() без аргументов, чтобы он сам рассчитал.
    # Или же, более сложная логика для adjust.
    # Пока что оставляем adjust(3) для примерного вида.

    # Кнопка "Назад"
    builder.add(types.InlineKeyboardButton(
        text="🔙 Назад к услугам",
        callback_data="back_to_service_choice"
    ))
    # adjust() без аргументов пытается распределить кнопки по рядам.
    # Но если у нас есть кнопка "Назад", которая добавляется отдельно,
    # лучше явно указать adjust для кнопок дней, а для "Назад" отдельно.
    # Или, просто использовать adjust(1) для всех, если ряды не критичны.
    # Здесь попробуем adjust(1) для всех, чтобы было предсказуемо.
    builder.adjust(1)  # Для всех кнопок, включая "Назад"

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