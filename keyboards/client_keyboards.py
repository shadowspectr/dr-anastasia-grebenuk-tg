from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_supabase import Database
from datetime import datetime, timedelta


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


async def get_services_keyboard(db: Database, category_id: str):
    builder = InlineKeyboardBuilder()
    # Используем await
    services = await db.get_services_by_category(category_id)
    for service in services:
        builder.add(
            InlineKeyboardButton(text=f"{service.title} ({service.price} ₽)", callback_data=f"service_{service.id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="client_book"))
    builder.adjust(1)
    return builder.as_markup()


def get_date_keyboard():
    # Эта функция не обращается к БД, остается синхронной
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    builder.add(InlineKeyboardButton(text="Сегодня", callback_data=f"date_{today.strftime('%Y-%m-%d')}"))
    builder.add(
        InlineKeyboardButton(text="Завтра", callback_data=f"date_{(today + timedelta(days=1)).strftime('%Y-%m-%d')}"))
    return builder.as_markup()


# --- НОВАЯ ФУНКЦИЯ ДЛЯ КАЛЕНДАРЯ ---
def get_date_keyboard(db: Database):
    """
    Создает клавиатуру с датами на неделю вперед, кроме сегодняшнего дня,
    и показывает только доступные для записи дни.
    """

    async def build_keyboard():
        builder = InlineKeyboardBuilder()
        today = datetime.now().date()

        # Покажем кнопки на 7 дней вперед (без сегодняшнего дня)
        for i in range(1, 8):  # От 1 до 7 дней
            current_date = today + timedelta(days=i)
            date_str = current_date.strftime('%Y-%m-%d')

            # --- Проверка доступности дня ---
            # Получаем записи на этот день, чтобы понять, свободен ли он.
            # Если нам нужно показать только дни, где есть свободные слоты,
            # то здесь нужно сделать запрос к БД.
            # Предположим, что мы хотим показать все дни, а доступность времени
            # проверим уже при выборе времени.
            # Если же хотим фильтровать дни:
            # appointments_on_day = await db.get_appointments_for_day(current_date)
            # if len(appointments_on_day) < MAX_SLOTS_PER_DAY: # Если есть свободные слоты
            #     builder.add(types.InlineKeyboardButton(
            #         text=f"{current_date.strftime('%d.%m')} ({current_date.strftime('%a')})",
            #         callback_data=f"date_{date_str}"
            #     ))
            # else:
            #     # Можно показать как недоступный или вообще не добавлять
            #     pass

            # Пока что просто добавляем все дни недели
            builder.add(types.InlineKeyboardButton(
                text=f"{current_date.strftime('%d.%m')} ({current_date.strftime('%a')})",  # Пример: 23.07 (Tue)
                callback_data=f"date_{date_str}"
            ))

        # Кнопка "Назад" для выбора услуги
        builder.add(types.InlineKeyboardButton(
            text="🔙 Назад к услугам",
            callback_data="back_to_service_choice"  # Нужно будет добавить этот callback в client_handlers
        ))
        builder.adjust(3)  # Например, 3 кнопки в ряду
        return builder.as_markup()

    return build_keyboard()


async def get_time_slots_keyboard(target_date: datetime, db: Database):
    """
    Создает клавиатуру со свободными слотами времени на выбранный день,
    учитывая уже занятые записи.
    """
    builder = InlineKeyboardBuilder()

    # Предполагаем, что у нас есть фиксированное время работы, например, с 9:00 до 18:00
    # и интервал между записями, например, 1 час.
    # Или же, что информация о свободных слотах берется из БД.

    # --- ЛОГИКА ОПРЕДЕЛЕНИЯ СВОБОДНЫХ СЛОТОВ ---
    # 1. Получаем все занятые записи на target_date
    try:
        # Здесь нужен метод, который вернет список занятых времен,
        # или же просто список объектов Appointment на этот день.
        # Если db.get_appointments_for_day возвращает список Appointment:
        appointments_on_day = await db.get_appointments_for_day(target_date)

        # Создаем множество занятых времен для быстрого поиска
        # Формат: "HH:MM"
        booked_times = {app.appointment_time.strftime('%H:%M') for app in appointments_on_day if app.appointment_time}

    except Exception as e:
        logger.error(f"Error fetching appointments for time slot check on {target_date.date()}: {e}")
        booked_times = set()  # Если произошла ошибка, считаем, что все свободно (или наоборот, показываем ошибку)

    # --- Генерируем доступные слоты ---
    # Допустим, рабочий день с 9:00 до 18:00, интервал 1 час
    start_hour = 9
    end_hour = 18
    slot_interval_minutes = 60  # Интервал между записями

    current_time = target_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)

    while current_time.hour < end_hour:
        slot_time_str = current_time.strftime('%H:%M')

        if slot_time_str not in booked_times:
            builder.add(types.InlineKeyboardButton(
                text=slot_time_str,
                callback_data=f"time_{slot_time_str}"
            ))
        else:
            # Можно показать как занятое, или просто не добавлять кнопку
            pass  # Не добавляем занятые слоты

        current_time += timedelta(minutes=slot_interval_minutes)

    # Кнопка "Назад" для выбора дня
    builder.add(types.InlineKeyboardButton(
        text="🔙 Назад к выбору дня",
        callback_data="back_to_date_choice"  # Этот callback уже есть
    ))
    builder.adjust(3)  # Например, 3 слота в ряду
    return builder.as_markup()


def get_confirmation_keyboard():
    # Эта функция не обращается к БД, остается синхронной
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="confirm_booking"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_booking"))
    return builder.as_markup()