import logging
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from datetime import datetime
from database.db_supabase import Database
from database.models import Appointment
from states.fsm_states import ClientStates
from keyboards.client_keyboards import *
from utils.notifications import notify_admin_on_new_booking
# Импортируем модуль google_calendar, чтобы получить доступ к функции create_google_calendar_event
import utils.google_calendar

router = Router()
logger = logging.getLogger(__name__)


# Старт флоу записи
@router.callback_query(F.data == "client_book")
async def client_start_booking(callback: types.CallbackQuery, state: FSMContext, db: Database):
    # Методы клавиатур теперь тоже могут быть асинхронными, если они делают запросы к БД
    keyboard = await get_service_categories_keyboard(db)
    await callback.message.edit_text("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_category)


# Шаг 2: Выбор категории
@router.callback_query(ClientStates.waiting_for_category, F.data.startswith("category_"))
async def client_pick_category(callback: types.CallbackQuery, state: FSMContext, db: Database):
    category_id = callback.data.split("_")[1]
    await state.update_data(category_id=category_id)
    keyboard = await get_services_keyboard(db, category_id)
    await callback.message.edit_text("Теперь выберите услугу:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_service)


# Шаг 3: Выбор услуги
@router.callback_query(ClientStates.waiting_for_service, F.data.startswith("service_"))
async def client_pick_service(callback: types.CallbackQuery, state: FSMContext, db: Database):
    service_id = callback.data.split("_")[1]
    # Используем await, так как метод теперь асинхронный
    service = await db.get_service_by_id(service_id)

    if not service:
        await callback.answer("Услуга не найдена, попробуйте снова.", show_alert=True)
        return

    await state.update_data(service_id=service_id, service_title=service.title, service_price=service.price)
    await callback.message.edit_text(f"Вы выбрали: {service.title}.\nТеперь выберите удобный день:",
                                     reply_markup=get_date_keyboard())
    await state.set_state(ClientStates.waiting_for_date)


@router.callback_query(F.data == "back_to_date_choice")
async def back_to_date_choice(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выберите удобный день:", reply_markup=get_date_keyboard())
    await state.set_state(ClientStates.waiting_for_date)


# Шаг 4: Выбор даты
@router.callback_query(ClientStates.waiting_for_date, F.data.startswith("date_"))
async def client_pick_date(callback: types.CallbackQuery, state: FSMContext, db: Database):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    # Здесь get_time_slots_keyboard скорее всего использует db для проверки доступности,
    # поэтому db передается. Если он не используется, можно убрать.
    keyboard = await get_time_slots_keyboard(target_date, db)
    await callback.message.edit_text(f"Выбрана дата: {date_str}.\nТеперь выберите свободное время:",
                                     reply_markup=keyboard)
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


@router.callback_query(ClientStates.waiting_for_confirmation, F.data == "confirm_booking")
async def client_confirm_booking(callback: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data()
    user = callback.from_user

    # Сохраняем выбранные данные
    await state.update_data(
        service_title=data['service_title'],
        service_price=data['service_price'],
        date=data['date'],
        time=data['time']
    )

    # Отправляем клиенту сообщение с запросом номера телефона
    await callback.message.edit_text(
        "Отлично! Теперь, пожалуйста, укажите ваш контактный номер телефона (например, +79991234567).")
    await state.set_state(ClientStates.waiting_for_phone)  # Переходим в состояние ожидания номера


# Шаг 7: Получение номера телефона
@router.message(ClientStates.waiting_for_phone)
async def client_provide_phone(message: types.Message, state: FSMContext, db: Database, bot: Bot):
    phone_number = message.text

    # TODO: Добавить валидацию номера телефона, если нужно (например, с помощью регулярных выражений)

    await state.update_data(phone_number=phone_number)  # Сохраняем номер телефона

    # Получаем все данные для финального подтверждения
    data = await state.get_data()

    # --- ФИНАЛЬНОЕ ПОДТВЕРЖДЕНИЕ ---
    text = (f"<b>Пожалуйста, проверьте детали вашей записи:</b>\n\n"
            f"<b>Услуга:</b> {data['service_title']}\n"
            f"<b>Стоимость:</b> {data['service_price']} ₽\n"
            f"<b>Дата:</b> {data['date']}\n"
            f"<b>Время:</b> {data['time']}\n"
            f"<b>Ваш номер:</b> {phone_number}")

    await message.answer(text,
                         reply_markup=get_confirmation_keyboard())  # Отправляем новое сообщение, чтобы не редактировать предыдущее
    await state.set_state(ClientStates.waiting_for_confirmation)


# --- ПЕРЕОПРЕДЕЛЕНИЕ КОНФИРМАЦИИ, ТАК КАК ТЕПЕРЬ У НАС ЕСТЬ НОМЕР ---

@router.callback_query(ClientStates.waiting_for_confirmation, F.data == "confirm_booking")
async def client_confirm_booking_final(callback: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data()
    user = callback.from_user

    appointment_dt = datetime.strptime(f"{data['date']} {data['time']}", '%Y-%m-%d %H:%M')

    # Создаем объект Appointment, теперь с номером телефона
    new_appointment = Appointment(
        client_name=user.full_name,
        client_telegram_id=user.id,
        service_id=data['service_id'],
        appointment_time=appointment_dt,
        client_phone=data.get('phone_number'),  # Получаем номер телефона из FSM состояния
        google_event_id=None  # Пока что None
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
            service_title=data['service_title'],
            service_price=data['service_price']
        )
        # ------------------------------------

        # --- ИНТЕГРАЦИЯ С GOOGLE CALENDAR ---
        service_duration = 60  # Фиксированная длительность в 1 час

        # Вызываем функцию создания события в Google Calendar, включая номер телефона
        google_event_id = utils.google_calendar.create_google_calendar_event(
            appointment_time_str=f"{data['date']} {data['time']}",
            service_title=data['service_title'],
            client_name=user.full_name,
            client_phone=data.get('phone_number'),  # Передаем номер телефона
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
            logger.warning(f"Не удалось создать событие для клиента {user.id} в Google Calendar.")
        # ------------------------------------

    else:
        await callback.message.edit_text("❌ Произошла ошибка при записи. Попробуйте позже.")

    await state.clear()


# Отмена на любом этапе
@router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Запись отменена.", reply_markup=get_client_main_keyboard())


# Отмена на любом этапе
@router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    # Отправляем сообщение об отмене и клавиатуру главного меню
    # Эта клавиатура не делает запросов в БД, поэтому await не нужен
    await callback.message.edit_text("Запись отменена.", reply_markup=get_client_main_keyboard())