# handlers/admin_handlers.py

import logging
from aiogram import Bot, Router, types, F
from aiogram.fsm.context import FSMContext
from config_reader import config
from datetime import datetime
import pytz  # <-- Добавляем импорт

from database.db_supabase import Database
from database.models import Appointment
from states.fsm_states import AdminStates
from keyboards.admin_keyboards import *
from keyboards.client_keyboards import (
    get_service_categories_keyboard,
    get_services_keyboard,
    get_upcoming_dates_keyboard,
    get_time_slots_keyboard
    # get_confirmation_keyboard нам не нужен, админ не подтверждает свою же запись
)
from utils.google_calendar import GoogleCalendar

router = Router()
# Фильтр, чтобы эти хэндлеры работали только для админа
router.message.filter(F.from_user.id == config.admin_id)
router.callback_query.filter(F.from_user.id == config.admin_id)

logger = logging.getLogger(__name__)
TIMEZONE = pytz.timezone('Europe/Moscow')


# --- Логика просмотра записей ---

@router.callback_query(F.data == "admin_today")
async def admin_today_appointments(callback: types.CallbackQuery, db: Database):
    logger.info("Admin requested today's appointments.")
    today = datetime.now(TIMEZONE)

    # Получаем события напрямую из Google Calendar
    events = await GoogleCalendar.get_events_with_details(today)  # Используем новый метод

    if not events:
        await callback.message.edit_text("📅 На сегодня записей нет.", reply_markup=get_admin_main_keyboard())
        return

    text = f"📅 <b>Записи на сегодня ({today.strftime('%d.%m.%Y')}):</b>\n\n"
    builder = InlineKeyboardBuilder()

    for event in sorted(events, key=lambda x: x['start']):
        event_start_time = event['start'].astimezone(TIMEZONE)
        summary = event.get('summary', 'Без названия')
        event_id = event.get('id')

        text += f"▪️ {event_start_time.strftime('%H:%M')} - {summary}\n"
        builder.add(types.InlineKeyboardButton(
            text=f"{event_start_time.strftime('%H:%M')} - {summary}",
            callback_data=f"admin_app_{event_id}"
        ))

    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 В главное меню", callback_data="admin_back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin_app_"))
async def admin_appointment_details(callback: types.CallbackQuery):
    event_id = callback.data.split("_")[2]
    await callback.message.edit_text(
        "Выберите действие для этой записи:",
        reply_markup=get_admin_appointment_actions_keyboard(event_id)
    )


@router.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete_appointment(callback: types.CallbackQuery, db: Database):
    event_id = callback.data.split("_")[2]
    logger.info(f"Admin trying to delete event with google_id: {event_id}")

    deleted_from_google = await GoogleCalendar.delete_event(event_id)

    if deleted_from_google:
        await db.delete_appointment_by_google_id(event_id)
        await callback.answer("Запись успешно удалена!", show_alert=True)
        # Вызываем функцию напрямую, так как callback уже использован
        await admin_today_appointments(callback, db)
    else:
        await callback.answer("Не удалось удалить запись из Google Календаря.", show_alert=True)


# --- ВЕТКА FSM ДЛЯ СОЗДАНИЯ ЗАПИСИ АДМИНОМ ---

@router.callback_query(F.data == "admin_new_appointment")
async def admin_start_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Введите имя клиента:")
    await state.set_state(AdminStates.waiting_for_client_name)


@router.message(AdminStates.waiting_for_client_name)
async def admin_enter_name(message: types.Message, state: FSMContext):
    await state.update_data(client_name=message.text)
    await message.answer("Теперь введите номер телефона клиента:")
    await state.set_state(AdminStates.waiting_for_client_phone)


@router.message(AdminStates.waiting_for_client_phone)
async def admin_enter_phone(message: types.Message, state: FSMContext, db: Database):
    await state.update_data(client_phone=message.text)
    keyboard = await get_service_categories_keyboard(db)
    await message.answer("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_service)


@router.callback_query(AdminStates.waiting_for_service, F.data.startswith("category_"))
async def admin_pick_category(callback: types.CallbackQuery, state: FSMContext, db: Database):
    category_id = callback.data.split("_")[1]
    keyboard = await get_services_keyboard(db, category_id)
    await callback.message.edit_text("Выберите услугу:", reply_markup=keyboard)
    # Состояние не меняем, просто обновляем клавиатуру


@router.callback_query(AdminStates.waiting_for_service, F.data.startswith("service_"))
async def admin_pick_service(callback: types.CallbackQuery, state: FSMContext, db: Database):
    service_id = callback.data.split("_")[1]
    service = await db.get_service_by_id(service_id)
    if not service:
        await callback.answer("Ошибка: не найдена услуга.", show_alert=True)
        return
    await state.update_data(service_id=service.id, service_title=service.title)
    keyboard = get_upcoming_dates_keyboard()
    await callback.message.edit_text("Выберите дату:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_date)


@router.callback_query(AdminStates.waiting_for_date, F.data.startswith("date_"))
async def admin_pick_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)
    target_date = datetime.fromisoformat(date_str)
    busy_slots = await GoogleCalendar.get_busy_slots(target_date)
    keyboard = get_time_slots_keyboard(target_date, busy_slots)
    await callback.message.edit_text(f"Выбрана дата: {target_date.strftime('%d.%m.%Y')}.\nВыберите время:",
                                     reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_time)


@router.callback_query(AdminStates.waiting_for_time, F.data.startswith("time_"))
async def admin_pick_time(callback: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    time_str = callback.data.split("_")[1]
    await state.update_data(time=time_str)

    # --- Финальное подтверждение и создание записи ---
    data = await state.get_data()

    naive_dt = datetime.strptime(f"{data['date']} {data['time']}", '%Y-%m-%d %H:%M')
    appointment_dt = TIMEZONE.localize(naive_dt)

    current_busy_slots = await GoogleCalendar.get_busy_slots(appointment_dt)
    is_slot_taken = any(
        slot.astimezone(TIMEZONE).time().hour == appointment_dt.time().hour for slot in current_busy_slots)

    if is_slot_taken:
        await callback.message.answer("Это время уже занято. Пожалуйста, выберите другое.")
        return

    google_event_id = await GoogleCalendar.add_appointment(
        client_name=data['client_name'],
        service_title=data['service_title'],
        appointment_time=appointment_dt,
        phone_number=data['client_phone']
    )

    if google_event_id:
        new_appointment = Appointment(
            client_name=data['client_name'],
            client_phone=data['client_phone'],
            service_id=data['service_id'],
            appointment_time=appointment_dt,
            google_event_id=google_event_id
        )
        await db.add_appointment(new_appointment)
        await callback.message.edit_text("✅ Запись успешно создана!")
    else:
        await callback.message.edit_text("❌ Не удалось создать запись в календаре.")

    await state.clear()


@router.callback_query(F.data == "admin_back_main")
async def admin_back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Добро пожаловать, Администратор!",
        reply_markup=get_admin_main_keyboard()
    )