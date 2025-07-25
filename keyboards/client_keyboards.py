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

    # --- ИЗМЕНЕНИЕ: Фильтруем дни недели ---
    # Доступные дни: вторник (1), четверг (3), пятница (4)
    # weekday() возвращает 0 для понедельника, 1 для вторника, ..., 6 для воскресенья.
    available_weekdays = {1, 3, 4}  # Tuesday, Thursday, Friday

    days_added = 0  # Счетчик, чтобы не показывать пустые ряды, если дни пропущены

    for i in range(1, 15):  # Проверяем на 2 недели вперед, чтобы гарантировать 3 дня
        current_date = today + timedelta(days=i)

        # Проверяем, является ли текущий день одним из доступных
        if current_date.weekday() in available_weekdays:
            date_str = current_date.strftime('%Y-%m-%d')
            builder.add(types.InlineKeyboardButton(
                text=f"{current_date.strftime('%d.%m')} ({current_date.strftime('%a')})",
                callback_data=f"date_{date_str}"
            ))
            days_added += 1
            if days_added % 3 == 0:  # Перенос на новую строку каждые 3 дня
                builder.adjust(3)  # Или adjust(2) или (1) в зависимости от желаемого вида

    # Если дни были добавлены, то adjust(3) уже был вызван
    # Если дней не нашлось (хотя при 15 днях это маловероятно), то adjust не вызывается

    # Кнопка "Назад" для выбора услуги
    builder.add(types.InlineKeyboardButton(
        text="🔙 Назад к услугам",
        callback_data="back_to_service_choice"
    ))
    # Adjust для кнопки "Назад"
    builder.adjust(1)  # Обычно кнопка "Назад" идет отдельно

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