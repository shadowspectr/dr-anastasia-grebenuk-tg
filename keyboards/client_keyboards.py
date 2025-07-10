from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db_supabase import Database
from datetime import datetime, timedelta


def get_client_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записаться на услугу", callback_data="client_book"))
    # Можно добавить "Мои записи", "Контакты" и т.д.
    return builder.as_markup()


def get_service_categories_keyboard(db: Database):
    builder = InlineKeyboardBuilder()
    categories = db.get_service_categories()
    for category in categories:
        builder.add(InlineKeyboardButton(text=category.title, callback_data=f"category_{category.id}"))
    builder.adjust(1)
    return builder.as_markup()


def get_services_keyboard(db: Database, category_id: str):
    builder = InlineKeyboardBuilder()
    services = db.get_services_by_category(category_id)
    for service in services:
        builder.add(
            InlineKeyboardButton(text=f"{service.title} ({service.price} ₽)", callback_data=f"service_{service.id}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="client_book"))
    builder.adjust(1)
    return builder.as_markup()


def get_date_keyboard():
    builder = InlineKeyboardBuilder()
    today = datetime.now()
    builder.add(InlineKeyboardButton(text="Сегодня", callback_data=f"date_{today.strftime('%Y-%m-%d')}"))
    builder.add(
        InlineKeyboardButton(text="Завтра", callback_data=f"date_{(today + timedelta(days=1)).strftime('%Y-%m-%d')}"))
    # Для полноценного календаря используйте библиотеку aiogram-calendar
    return builder.as_markup()


def get_time_slots_keyboard(target_date: datetime, db: Database):
    builder = InlineKeyboardBuilder()
    appointments = db.get_appointments_for_day(target_date, status='active')
    busy_times = [app.appointment_time.time() for app in appointments]

    time_slots = []
    for hour in range(9, 19):  # с 9:00 до 18:30
        for minute in [0, 30]:
            if target_date.date() == datetime.now().date() and hour < datetime.now().hour:
                continue  # Пропускаем прошедшие часы для сегодня
            time_slot = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
            if time_slot not in busy_times:
                time_slots.append(time_slot)

    if not time_slots:
        builder.add(InlineKeyboardButton(text="❌ Нет свободного времени", callback_data="no_slots"))
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