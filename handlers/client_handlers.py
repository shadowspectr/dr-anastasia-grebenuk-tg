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


# --- НОВЫЙ ОБРАБОТЧИК ДЛЯ ВОЗВРАТА К ВЫБОРУ КАТЕГОРИИ ---
@router.callback_query(ClientStates.waiting_for_service, F.data == "back_to_category_choice")
async def back_to_category_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    # Удаляем данные о выбранной услуге
    await state.unset_data("service_id")
    await state.unset_data("service_title")
    await state.unset_data("service_price")

    # Возвращаемся к выбору категории
    keyboard = await get_service_categories_keyboard(db)
    await callback.message.edit_text("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_category)


# --- КОНЕЦ НОВОГО ОБРАБОТЧИКА ---


# Шаг 3: Выбор услуги
@router.callback_query(ClientStates.waiting_for_service, F.data.startswith("service_"))
async def client_pick_service(callback: types.CallbackQuery, state: FSMContext, db: Database):
    service_id = callback.data.split("_")[1]
    service = await db.get_service_by_id(service_id)

    if not service:
        await callback.answer("Услуга не найдена, попробуйте снова.", show_alert=True)
        return

    await state.update_data(service_id=service_id, service_title=service.title, service_price=service.price)

    # --- ИСПРАВЛЕНИЕ: Теперь get_date_keyboard - async функция, поэтому ее нужно await'ить ---
    keyboard = await get_date_keyboard(db)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    await callback.message.edit_text(f"Вы выбрали: {service.title}.\nТеперь выберите удобный день:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_date)


# --- ОБРАБОТЧИК ВОЗВРАТА К ВЫБОРУ ДАТЫ ---
@router.callback_query(ClientStates.waiting_for_time, F.data == "back_to_date_choice")
async def back_to_date_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    # Удаляем данные о выбранном времени
    await state.unset_data("time")

    # Получаем сохраненную дату
    data = await state.get_data()
    date_str = data.get('date')
    if not date_str:
        await callback.answer("Не удалось определить выбранную дату.", show_alert=True)
        # Можно вернуть на предыдущий шаг или главную меню
        return await state.finish()

    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    keyboard = await get_time_slots_keyboard(target_date, db)  # Показываем слоты на тот же день
    await callback.message.edit_text(f"Выбрана дата: {date_str}.\nТеперь выберите свободное время:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_time)  # Остаемся в том же состоянии


# --- КОНЕЦ ОБРАБОТЧИКА ВОЗВРАТА ---


# Шаг 4: Выбор даты
@router.callback_query(ClientStates.waiting_for_date, F.data.startswith("date_"))
async def client_pick_date(callback: types.CallbackQuery, state: FSMContext, db: Database):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)
    target_date = datetime.strptime(date_str, '%Y-%m-%d')

    # --- ИЗМЕНЕНИЕ: Получаем слоты времени на выбранную дату ---
    keyboard = await get_time_slots_keyboard(target_date, db)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    await callback.message.edit_text(f"Выбрана дата: {date_str}.\nТеперь выберите свободное время:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_time)


# Шаг 5: Выбор времени
@router.callback_query(ClientStates.waiting_for_time, F.data.startswith("time_"))
async def client_pick_time(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_")[1]
    await state.update_data(time=time_str)

    # Получаем все собранные данные для финального подтверждения
    data = await state.get_data()

    text = (f"<b>Подтвердите вашу запись:</b>\n\n"
            f"<b>Услуга:</b> {data['service_title']}\n"
            f"<b>Стоимость:</b> {data['service_price']} ₽\n"
            f"<b>Дата:</b> {data['date']}\n"
            f"<b>Время:</b> {time_str}")  # Используем time_str напрямую

    await callback.message.edit_text(text, reply_markup=get_confirmation_keyboard())
    await state.set_state(ClientStates.waiting_for_confirmation)


# Шаг 6: Запрос номера телефона (новый шаг)
@router.callback_query(ClientStates.waiting_for_confirmation, F.data == "confirm_booking")
async def client_request_phone_number(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Отлично! Теперь, пожалуйста, укажите ваш контактный номер телефона (например, +79991234567).")
    await state.set_state(ClientStates.waiting_for_phone)  # Переходим в состояние ожидания номера


# Шаг 7: Получение номера телефона и финальное подтверждение
@router.message(ClientStates.waiting_for_phone)
async def client_provide_phone(message: types.Message, state: FSMContext, db: Database, bot: Bot):
    phone_number = message.text

    # TODO: Добавить валидацию номера телефона, если нужно (например, с помощью регулярных выражений)

    await state.update_data(phone_number=phone_number)  # Сохраняем номер телефона

    # Получаем ВСЕ данные для финального подтверждения
    data = await state.get_data()

    text = (f"<b>Пожалуйста, проверьте детали вашей записи:</b>\n\n"
            f"<b>Услуга:</b> {data['service_title']}\n"
            f"<b>Стоимость:</b> {data['service_price']} ₽\n"
            f"<b>Дата:</b> {data['date']}\n"
            f"<b>Время:</b> {data['time']}\n"
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

    # Добавляем запись в базу данных
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

        # Вызываем функцию создания события в Google Calendar, передавая номер телефона
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