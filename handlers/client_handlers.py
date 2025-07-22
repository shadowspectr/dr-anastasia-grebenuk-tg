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


# Старт флоу записи
@router.callback_query(F.data == "client_book")
async def client_start_booking(callback: types.CallbackQuery, state: FSMContext, db: Database):
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


# --- Обработчик возврата к выбору категорий ---
@router.callback_query(ClientStates.waiting_for_service, F.data == "back_to_category_choice")
async def back_to_category_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    await state.unset_data("service_id")
    await state.unset_data("service_title")
    await state.unset_data("service_price")

    keyboard = await get_service_categories_keyboard(db)
    await callback.message.edit_text("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_category)


# Шаг 3: Выбор услуги
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


# Шаг 4: Выбор даты
@router.callback_query(ClientStates.waiting_for_date, F.data.startswith("date_"))
async def client_pick_date(callback: types.CallbackQuery, state: FSMContext, db: Database):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)
    target_date = datetime.strptime(date_str, '%Y-%m-%d')

    keyboard = await get_time_slots_keyboard(target_date, db)
    await callback.message.edit_text(f"Выбрана дата: {date_str}.\nТеперь выберите свободное время:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_time)


# --- Обработчик возврата к выбору дня ---
@router.callback_query(ClientStates.waiting_for_time, F.data == "back_to_date_choice")
async def back_to_date_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    await state.unset_data("time")  # Удаляем выбранное время

    data = await state.get_data()
    date_str = data.get('date')
    if not date_str:
        await callback.answer("Не удалось определить выбранную дату.", show_alert=True)
        return await state.finish()  # Или вернуть на главный экран

    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    keyboard = await get_time_slots_keyboard(target_date, db)  # Пересоздаем клавиатуру времени
    await callback.message.edit_text(f"Выбрана дата: {date_str}.\nТеперь выберите свободное время:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_time)  # Остаемся в том же состоянии


# Шаг 5: Выбор времени
@router.callback_query(ClientStates.waiting_for_time, F.data.startswith("time_"))
async def client_pick_time(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_")[1]

    # Сохраняем всю информацию перед переходом к запросу номера
    await state.update_data(time=time_str)
    data = await state.get_data()  # Получаем все собранные данные

    # Теперь сразу запрашиваем номер телефона
    await callback.message.edit_text(
        "Отлично! Теперь, пожалуйста, укажите ваш контактный номер телефона (например, +79991234567).")
    await state.set_state(ClientStates.waiting_for_phone)  # Переходим в состояние ожидания номера


# --- Шаг 6: Получение номера телефона И финальное подтверждение ---
# Этот обработчик теперь отвечает за ПОЛУЧЕНИЕ номера и ПОКАЗ финального подтверждения.
@router.message(ClientStates.waiting_for_phone)
async def client_provide_phone_and_confirm(message: types.Message, state: FSMContext, db: Database, bot: Bot):
    phone_number = message.text

    # TODO: Добавить валидацию номера телефона, если нужно

    await state.update_data(phone_number=phone_number)  # Сохраняем номер телефона

    # Получаем ВСЕ собранные данные для финального подтверждения
    data = await state.get_data()

    # Формируем финальный текст подтверждения
    text = (f"<b>Пожалуйста, проверьте детали вашей записи:</b>\n\n"
            f"<b>Услуга:</b> {data.get('service_title', 'Не указано')}\n"
            f"<b>Стоимость:</b> {data.get('service_price', 'Не указано')} ₽\n"
            f"<b>Дата:</b> {data.get('date', 'Не указано')}\n"
            f"<b>Время:</b> {data.get('time', 'Не указано')}\n"
            f"<b>Ваш номер:</b> {phone_number}")  # Отображаем введенный номер

    # Отправляем НОВОЕ сообщение с финальным подтверждением.
    # Редактирование предыдущего сообщения (от бота) может быть некорректным,
    # если оно было изменено клиентом (его сообщением с номером).
    await message.answer(text, reply_markup=get_confirmation_keyboard())
    await state.set_state(ClientStates.waiting_for_confirmation)  # Переходим в состояние финального подтверждения


# --- ОБРАБОТЧИК ФИНАЛЬНОГО ПОДТВЕРЖДЕНИЯ ---
# Этот обработчик теперь будет срабатывать, когда клиент нажмет "Подтвердить"
# после того, как указал номер телефона.
@router.callback_query(ClientStates.waiting_for_confirmation, F.data == "confirm_booking")
async def client_confirm_booking_final(callback: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data()
    user = callback.from_user

    # Проверяем, есть ли все необходимые данные
    required_keys = ['service_title', 'service_price', 'date', 'time', 'phone_number']
    if not all(key in data and data[key] for key in required_keys):
        logger.error(f"Missing data for final confirmation: {data}. User: {user.id}")
        await callback.answer("Произошла ошибка при сборе данных. Попробуйте начать запись заново.", show_alert=True)
        await state.clear()
        return

    appointment_dt = datetime.strptime(f"{data['date']} {data['time']}", '%Y-%m-%d %H:%M')

    # Создаем объект Appointment
    new_appointment = Appointment(
        client_name=user.full_name,
        client_telegram_id=user.id,
        service_id=data['service_id'],
        appointment_time=appointment_dt,
        client_phone=data.get('phone_number'),
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
        service_duration = 60

        google_event_id = utils.google_calendar.create_google_calendar_event(
            appointment_time_str=f"{data['date']} {data['time']}",
            service_title=data['service_title'],
            client_name=user.full_name,
            client_phone=data.get('phone_number'),
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