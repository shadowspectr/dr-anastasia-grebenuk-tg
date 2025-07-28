# handlers/client_handlers.py

import logging
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from datetime import datetime
from database.db_supabase import Database
from database.models import Appointment
from states.fsm_states import ClientStates
from keyboards.client_keyboards import *
from utils.notifications import notify_admin_on_new_booking
import utils.google_calendar

router = Router()
logger = logging.getLogger(__name__)


# --- Старт флоу записи ---
@router.callback_query(F.data == "client_book")
async def client_start_booking(callback: types.CallbackQuery, state: FSMContext, db: Database):
    logger.info(f"User {callback.from_user.id} started booking.")
    keyboard = await get_service_categories_keyboard(db)
    await callback.message.edit_text("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_category)


# --- Шаг 2: Выбор категории ---
@router.callback_query(ClientStates.waiting_for_category, F.data.startswith("category_"))
async def client_pick_category(callback: types.CallbackQuery, state: FSMContext, db: Database):
    category_id = callback.data.split("_")[1]
    await state.update_data(category_id=category_id)
    keyboard = await get_services_keyboard(db, category_id)
    await callback.message.edit_text("Теперь выберите услугу:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_service)


# --- Обработчик возврата от выбора услуг к категориям ---
@router.callback_query(ClientStates.waiting_for_service, F.data == "back_to_category_choice")
async def client_back_to_category_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(service_id=None, service_title=None, service_price=None)

    keyboard = await get_service_categories_keyboard(db)
    await callback.message.edit_text("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_category)


# --- Шаг 3: Выбор услуги ---
@router.callback_query(ClientStates.waiting_for_service, F.data.startswith("service_"))
async def client_pick_service(callback: types.CallbackQuery, state: FSMContext, db: Database):
    service_id = callback.data.split("_")[1]
    service = await db.get_service_by_id(service_id)

    if not service:
        await callback.answer("Услуга не найдена, попробуйте снова.", show_alert=True)
        return

    await state.update_data(service_id=service_id, service_title=service.title, service_price=service.price)
    keyboard = await get_date_keyboard(db)
    await callback.message.edit_text(f"Вы выбрали: {service.title}.\nТеперь выберите удобный день:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_date)


# --- Обработчик возврата от выбора времени к выбору даты ---
@router.callback_query(ClientStates.waiting_for_time, F.data == "back_to_date_choice")
async def client_back_to_date_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(time=None)

    data = await state.get_data()
    date_str = data.get('date')
    if not date_str:
        await callback.answer("Не удалось определить выбранную дату.", show_alert=True)
        await state.finish()
        return

    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    keyboard = await get_time_slots_keyboard(target_date, db)
    await callback.message.edit_text(f"Выбрана дата: {date_str}.\nТеперь выберите свободное время:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_time)


# --- Шаг 4: Выбор даты ---
@router.callback_query(ClientStates.waiting_for_date, F.data.startswith("date_"))
async def client_pick_date(callback: types.CallbackQuery, state: FSMContext, db: Database):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    keyboard = await get_time_slots_keyboard(target_date, db)
    await callback.message.edit_text(f"Выбрана дата: {date_str}.\nТеперь выберите свободное время:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_time)


# --- Шаг 5: Выбор времени ---
@router.callback_query(ClientStates.waiting_for_time, F.data.startswith("time_"))
async def client_pick_time(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_")[1]
    await state.update_data(time=time_str)

    data = await state.get_data()

    # --- Теперь сразу показываем финальное подтверждение, но с запросом номера ---
    text = (f"<b>Подтвердите вашу запись:</b>\n\n"
            f"<b>Услуга:</b> {data.get('service_title', 'Не указано')}\n"
            f"<b>Стоимость:</b> {data.get('service_price', 'Не указано')} ₽\n"
            f"<b>Дата:</b> {data.get('date', 'Не указано')}\n"
            f"<b>Время:</b> {time_str}")  # Используем time_str напрямую

    await callback.message.edit_text(text,
                                     reply_markup=get_confirmation_keyboard())  # Показываем кнопки подтверждения/отмены
    await state.set_state(ClientStates.waiting_for_phone)  # Переходим в состояние ожидания номера


# --- Шаг 6: Получение номера телефона ---
@router.message(ClientStates.waiting_for_phone)
async def client_provide_phone(message: types.Message, state: FSMContext, db: Database, bot: Bot):
    phone_number = message.text
    await state.update_data(phone_number=phone_number)  # Сохраняем номер телефона

    data = await state.get_data()

    # Формируем финальный текст подтверждения, теперь с номером телефона
    text = (f"<b>Пожалуйста, проверьте детали вашей записи:</b>\n\n"
            f"<b>Услуга:</b> {data.get('service_title', 'Не указано')}\n"
            f"<b>Стоимость:</b> {data.get('service_price', 'Не указано')} ₽\n"
            f"<b>Дата:</b> {data.get('date', 'Не указано')}\n"
            f"<b>Время:</b> {data.get('time', 'Не указано')}\n"
            f"<b>Ваш номер:</b> {phone_number}")  # Используем введенный номер

    await message.answer(text, reply_markup=get_confirmation_keyboard())  # Отправляем новое сообщение с кнопками
    await state.set_state(ClientStates.waiting_for_confirmation)  # Переходим в состояние финального подтверждения


# --- Шаг 7: Финальное подтверждение записи ---
# Этот обработчик срабатывает, когда клиент нажимает "Подтвердить" после ввода номера.
@router.callback_query(ClientStates.waiting_for_confirmation, F.data == "confirm_booking")
async def client_confirm_booking_final(callback: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data()
    user = callback.from_user  # Получаем пользователя, который нажал кнопку

    client_name = data.get('client_name')  # Имя берется из FSM
    service_id = data.get('service_id')
    service_title = data.get('service_title')
    service_price = data.get('service_price')
    date_str = data.get('date')
    time_str = data.get('time')
    phone_number = data.get('phone_number')

    if not all([client_name, service_id, service_title, date_str, time_str, phone_number]):
        await callback.answer("Недостаточно данных для записи. Пожалуйста, начните заново.", show_alert=True)
        await state.clear()
        return

    try:
        appointment_dt = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
    except ValueError:
        await callback.answer("Ошибка в формате даты или времени.", show_alert=True)
        await state.clear()
        return

    new_appointment = Appointment(
        client_name=client_name,  # Имя клиента
        client_telegram_id=user.id,  # ID клиента, который нажал кнопку
        service_id=service_id,
        appointment_time=appointment_dt,
        client_phone=phone_number,
        google_event_id=None
    )

    appointment_id = await db.add_appointment(new_appointment)

    if appointment_id:
        await callback.message.edit_text(
            "✅ Вы успешно записаны!\n\n"
            "Вам придет напоминание за день до визита. Ждем вас!"
        )

        # --- Уведомление администратору ---
        new_appointment.id = appointment_id
        await notify_admin_on_new_booking(
            bot=bot,
            appointment=new_appointment,
            service_title=service_title,
            service_price=service_price
        )
        # ------------------------------------

        # --- ИНТЕГРАЦИЯ С GOOGLE CALENDAR ---
        service_duration = 60
        google_event_id = utils.google_calendar.create_google_calendar_event(
            appointment_time_str=f"{date_str} {time_str}",
            service_title=service_title,
            client_name=client_name,
            client_phone=phone_number,
            service_duration_minutes=service_duration
        )

        if google_event_id:
            logger.info(f"Событие Google Calendar с ID '{google_event_id}' успешно создано для клиента {user.id}.")
            if await db.update_appointment_google_id(appointment_id, google_event_id):
                logger.info(f"Google Event ID '{google_event_id}' успешно сохранен для записи '{appointment_id}'.")
            else:
                logger.warning(
                    f"Не удалось сохранить Google Event ID '{google_event_id}' для записи '{appointment_id}'.")
        else:
            logger.warning(f"Не удалось создать событие Google Calendar для клиента {user.id}.")
        # ------------------------------------

    else:
        await callback.message.edit_text("❌ Произошла ошибка при записи. Попробуйте позже.")

    await state.clear()


# Отмена на любом этапе
@router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Запись отменена.", reply_markup=get_client_main_keyboard())