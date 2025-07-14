# keyboards/client_keyboards.py

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_supabase import Database
from datetime import datetime, timedelta
from typing import List
from aiogram_calendar import SimpleCalendar, get_user_locale, SimpleCalendarCallback

def get_client_main_keyboard():
    """Возвращает главную клавиатуру клиента."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записаться на услугу", callback_data="client_book"))
    # Можно добавить другие кнопки: "Мои записи", "Контакты"
    return builder.as_markup()


async def get_service_categories_keyboard(db: Database):
    """Генерирует клавиатуру с категориями услуг из БД."""
    builder = InlineKeyboardBuilder()
    categories = await db.get_service_categories()
    for category in categories:
        builder.add(InlineKeyboardButton(text=category.title, callback_data=f"category_{category.id}"))
    builder.adjust(1)
    return builder.as_markup()


async def get_services_keyboard(db: Database, category_id: str):
    """Генерирует клавиатуру с услугами для выбранной категории."""
    builder = InlineKeyboardBuilder()
    services = await db.get_services_by_category(category_id)
    for service in services:
        builder.add(
            InlineKeyboardButton(text=f"{service.title} ({service.price} ₽)", callback_data=f"service_{service.id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="client_book"))
    builder.adjust(1)
    return builder.as_markup()


def get_date_keyboard():
    """Генерирует простую клавиатуру для выбора дня."""
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    builder.add(InlineKeyboardButton(text="Сегодня", callback_data=f"date_{today.strftime('%Y-%m-%d')}"))
    builder.add(
        InlineKeyboardButton(text="Завтра", callback_data=f"date_{(today + timedelta(days=1)).strftime('%Y-%m-%d')}"))
    # Для полноценного календаря можно использовать библиотеку aiogram-calendar
    return builder.as_markup()


def get_time_slots_keyboard(target_date: datetime, busy_slots: List[datetime]):
    """
    Генерирует клавиатуру со свободными временными слотами.
    Принимает список уже занятых слотов.
    """
    builder = InlineKeyboardBuilder()
    # Получаем только время из объектов datetime (и приводим к нужному часовому поясу, если нужно)
    busy_times = [slot.astimezone().time() for slot in busy_slots]

    time_slots = []
    # Генерируем слоты с 9:00 до 18:30
    for hour in range(9, 19):
        for minute in [0, 30]:
            # Пропускаем прошедшие часы для сегодня
            if target_date.date() == datetime.now().date() and hour < datetime.now().hour:
                continue

            time_slot = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
            if time_slot not in busy_times:
                time_slots.append(time_slot)

    if not time_slots:
        builder.add(InlineKeyboardButton(text="❌ На эту дату нет свободного времени", callback_data="no_slots"))
    else:
        for time_slot in time_slots:
            builder.add(InlineKeyboardButton(text=time_slot.strftime("%H:%M"),
                                             callback_data=f"time_{time_slot.strftime('%H:%M')}"))

    builder.add(InlineKeyboardButton(text="🔙 Назад к выбору даты", callback_data="back_to_date_choice"))
    builder.adjust(4)  # Располагаем по 4 кнопки в ряд
    return builder.as_markup()


async def get_calendar_keyboard():
    """
    Создает инлайн-календарь для выбора даты.
    Запрещает выбирать прошедшие даты.
    """
    # Создаем календарь. Можно локализовать, но для простоты оставим английские названия.
    simple_calendar = SimpleCalendar(
        locale='ru_RU',  # Используем русскую локаль
        show_alerts=True
    )
    # Устанавливаем минимальную возможную дату - сегодня
    simple_calendar.set_dates_range(
        from_date=datetime.now() - timedelta(days=1),  # -1 чтобы сегодняшний день был доступен
        to_date=datetime.now() + timedelta(days=60)  # Ограничиваем запись 2 месяцами вперед
    )
    return simple_calendar.start_calendar()


def get_time_slots_keyboard(target_date: datetime, busy_slots: List[datetime]):
    """
    Генерирует клавиатуру со свободными временными слотами.
    Принимает список уже занятых слотов.
    """
    builder = InlineKeyboardBuilder()
    # Приводим время к часовому поясу системы, если оно с таймзоной
    busy_times = [slot.astimezone().time() for slot in busy_slots]

    time_slots = []
    # Генерируем слоты с 9:00 до 18:30
    for hour in range(9, 19):
        for minute in [0, 30]:
            current_slot_time = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()

            # Пропускаем прошедшие часы для сегодня
            if target_date.date() == datetime.now().date() and current_slot_time <= datetime.now().time():
                continue

            if current_slot_time not in busy_times:
                time_slots.append(current_slot_time)

    if not time_slots:
        builder.add(InlineKeyboardButton(text="❌ На эту дату нет свободного времени", callback_data="no_slots"))
    else:
        for time_slot in time_slots:
            builder.add(InlineKeyboardButton(text=time_slot.strftime("%H:%M"),
                                             callback_data=f"time_{time_slot.strftime('%H:%M')}"))

    # Кнопка для возврата к календарю
    builder.add(InlineKeyboardButton(text="🔙 Назад к выбору даты", callback_data="back_to_calendar"))
    builder.adjust(4)  # Располагаем по 4 кнопки в ряд
    return builder.as_markup()


def get_confirmation_keyboard():
    """Возвращает клавиатуру для подтверждения или отмены записи."""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="confirm_booking"))
    builder.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_booking"))
    return builder.as_markup()