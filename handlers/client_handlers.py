# handlers/client_handlers.py

import logging
from aiogram import Bot, Router, types, F
from aiogram.fsm.context import FSMContext
from datetime import datetime, date

from database.db_supabase import Database
from database.models import Appointment
from states.fsm_states import ClientStates
from keyboards.client_keyboards import *
from utils.google_calendar import GoogleCalendar
from utils.notifications import notify_admin_on_new_appointment

router = Router()
logger = logging.getLogger(__name__)


# --- Логика до выбора услуги остается без изменений ---

@router.callback_query(F.data == "client_book")
async def client_start_booking(callback: types.CallbackQuery, state: FSMContext, db: Database):
    keyboard = await get_service_categories_keyboard(db)
    await callback.message.edit_text("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_category)


@router.callback_query(ClientStates.waiting_for_category, F.data.startswith("category_"))
async def client_pick_category(callback: types.CallbackQuery, state: FSMContext, db: Database):
    category_id = callback.data.split("_")[1]
    await state.update_data(category_id=category_id)
    keyboard = await get_services_keyboard(db, category_id)
    await callback.message.edit_text("Теперь выберите услугу:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_service)


# --- ИЗМЕНЕННАЯ ЛОГИКА ---

# Шаг 3: Выбор услуги. Показываем нашу новую клавиатуру дат.
@router.callback_query(ClientStates.waiting_for_service, F.data.startswith("service_"))
async def client_pick_service(callback: types.CallbackQuery, state: FSMContext, db: Database):
    service_id = callback.data.split("_")[1]
    service = await db.get_service_by_id(service_id)
    if not service:
        await callback.answer("Услуга не найдена, попробуйте снова.", show_alert=True)
        return

    await state.update_data(service_id=service_id, service_title=service.title, service_price=service.price,
                            duration_minutes=120)  # Сохраняем длительность

    keyboard = get_upcoming_dates_keyboard()
    await callback.message.edit_text(
        f"Вы выбрали: {service.title}.\n\n🗓️ Теперь выберите удобную дату:",
        reply_markup=keyboard
    )
    await state.set_state(ClientStates.waiting_for_date)


# Хендлер для возврата к выбору даты
@router.callback_query(F.data == "back_to_date_choice")
async def back_to_date_handler(callback: types.CallbackQuery, state: FSMContext):
    keyboard = get_upcoming_dates_keyboard()
    await callback.message.edit_text("🗓️ Пожалуйста, выберите дату:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_date)


# Шаг 4: Обработка выбора даты
@router.callback_query(ClientStates.waiting_for_date, F.data.startswith("date_"))
async def client_pick_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)

    # Используем fromisoformat, так как date_str в формате YYYY-MM-DD
    target_date = datetime.fromisoformat(date_str)

    busy_slots = await GoogleCalendar.get_busy_slots(target_date)
    keyboard = get_time_slots_keyboard(target_date, busy_slots)

    await callback.message.edit_text(
        f"Выбрана дата: {target_date.strftime('%d.%m.%Y')}.\nТеперь выберите свободное время:",
        reply_markup=keyboard
    )
    await state.set_state(ClientStates.waiting_for_time)


# Шаг 5: Выбор времени
@router.callback_query(ClientStates.waiting_for_time, F.data.startswith("time_"))
async def client_pick_time(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_")[1]
    await state.update_data(time=time_str)
    data = await state.get_data()
    text = (f"<b>Подтвердите вашу запись:</b>\n\n"
            f"<b>Услуга:</b> {data['service_title']}\n"
            f"<b>Стоимость:</b> {data['service_price']} ₽\n"
            f"<b>Дата:</b> {data['date']}\n"
            f"<b>Время:</b> {data['time']}")
    await callback.message.edit_text(text, reply_markup=get_confirmation_keyboard())
    await state.set_state(ClientStates.waiting_for_confirmation)


# Шаг 6: Запрос телефона
@router.callback_query(ClientStates.waiting_for_confirmation, F.data == "confirm_booking")
async def client_request_phone(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Отлично! Для завершения записи, пожалуйста, введите ваш номер телефона для связи:")
    await state.set_state(ClientStates.waiting_for_phone)


# Шаг 7: Финальное подтверждение с проверкой занятости
@router.message(ClientStates.waiting_for_phone)
async def client_process_booking_with_phone(message: types.Message, state: FSMContext, db: Database, bot: Bot):
    phone_number = message.text
    await message.answer("Минутку, проверяю и создаю запись...")

    data = await state.get_data()
    user = message.from_user
    appointment_dt = datetime.strptime(f"{data['date']} {data['time']}", '%Y-%m-%d %H:%M')

    # --- Усиленная проверка занятости ---
    logger.info(f"Final check for slot {appointment_dt}...")
    current_busy_slots = await GoogleCalendar.get_busy_slots(appointment_dt)

    appointment_start_hour = appointment_dt.time().hour
    is_slot_taken = any(
        slot.astimezone().time().hour in [appointment_start_hour, appointment_start_hour + 1]
        for slot in current_busy_slots
    )

    if is_slot_taken:
        logger.warning(f"Slot {appointment_dt} was taken by another user. Aborting.")
        await message.answer("К сожалению, кто-то только что занял это время. 😟\nПожалуйста, начните запись заново.")
        await state.clear()
        return

    # --- Конец проверки ---

    logger.info("Slot is free. Attempting to create event in Google Calendar...")
    google_event_id = await GoogleCalendar.add_appointment(
        client_name=user.full_name,
        service_title=data['service_title'],
        appointment_time=appointment_dt,
        phone_number=phone_number,
        duration_minutes=data.get('duration_minutes', 120)  # Используем сохраненную длительность
    )

    if google_event_id:
        logger.info(f"Google Calendar event created: {google_event_id}. Saving to DB...")
        new_appointment = Appointment(client_name=user.full_name, client_telegram_id=user.id,
                                      service_id=data['service_id'], appointment_time=appointment_dt)
        db_appointment_id = await db.add_appointment(new_appointment)
        if db_appointment_id:
            logger.info(f"Appointment saved to DB with ID: {db_appointment_id}")
            await notify_admin_on_new_appointment(bot, new_appointment, data['service_title'], phone_number)
            await message.answer("✅ Вы успешно записаны!\nЗапись добавлена в календарь и нашу систему.")
        else:
            logger.error("Failed to save appointment to DB after creating it in Google Calendar.")
            await message.answer(
                "❌ Произошла ошибка при сохранении записи в нашу систему. Пожалуйста, свяжитесь с администратором.")
    else:
        logger.error("Failed to create event in Google Calendar.")
        await message.answer(
            "❌ Произошла ошибка при записи в календарь. Свободное время могло измениться. Попробуйте снова.")

    await state.clear()


# Отмена
@router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Запись отменена.", reply_markup=get_client_main_keyboard())