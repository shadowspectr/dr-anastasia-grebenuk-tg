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

    # --- ИСПРАВЛЕНИЕ: Теперь get_services_keyboard - async, нужно await ---
    keyboard = await get_services_keyboard(db, category_id)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    await callback.message.edit_text("Теперь выберите услугу:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_service)


# --- Обработчик возврата к выбору категорий ---
@router.callback_query(ClientStates.waiting_for_service, F.data == "back_to_category_choice")
async def back_to_category_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    logger.info("User requested to go back to category selection.")

    # --- ИСПРАВЛЕНИЕ: Используем update_data(key=None) вместо unset_data ---
    await state.update_data(service_id=None)
    await state.update_data(service_title=None)
    await state.update_data(service_price=None)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

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

    # --- ИСПРАВЛЕНИЕ: Убедитесь, что get_date_keyboard await-ится ---
    keyboard = await get_date_keyboard(db)  # <-- ДОЛЖНО БЫТЬ AWAIT
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    await callback.message.edit_text(f"Вы выбрали: {service.title}.\nТеперь выберите удобный день:",
                                     reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_date)


# --- ОБРАБОТЧИК ВОЗВРАТА К ВЫБОРУ УСЛУГ ---
# --- ОБРАБОТЧИК ВОЗВРАТА К ВЫБОРУ УСЛУГ ---
@router.callback_query(ClientStates.waiting_for_date, F.data == "back_to_service_choice")
async def back_to_service_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    logger.info("User requested to go back to service selection.")

    # --- ИСПРАВЛЕНИЕ: Используем update_data(key=None) вместо unset_data ---
    await state.update_data(date=None)  # Удаляем выбранную дату
    await state.update_data(time=None)  # Удаляем выбранное время (если оно было сохранено)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    # Получаем сохраненные данные о категории
    data = await state.get_data()
    category_id = data.get('category_id')

    if not category_id:
        await callback.answer("Не удалось определить выбранную категорию.", show_alert=True)
        await state.finish()
        return

    # Возвращаемся к выбору услуг
    keyboard = await get_services_keyboard(db, category_id)
    await callback.message.edit_text("Теперь выберите услугу:", reply_markup=keyboard)
    await state.set_state(ClientStates.waiting_for_service)  # Возвращаем состояние


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


# --- ОБРАБОТЧИК ВОЗВРАТА К ВЫБОРУ ДНЯ ---
@router.callback_query(ClientStates.waiting_for_time, F.data == "back_to_date_choice")
async def back_to_date_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    # --- ИСПРАВЛЕНИЕ: Удаляем данные корректным образом ---
    # Вместо unset_data, используем update_data с None
    await state.update_data(time=None)
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    data = await state.get_data()
    date_str = data.get('date')
    if not date_str:
        await callback.answer("Не удалось определить выбранную дату.", show_alert=True)
        return await state.finish()

    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    keyboard = await get_time_slots_keyboard(target_date, db)
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

    client_name = data.get('client_name')
    service_id = data.get('service_id')
    service_title = data.get('service_title')
    service_price = data.get('service_price')
    date_str = data.get('date')
    time_str = data.get('time')
    phone_number = data.get('phone_number')  # <-- Убедитесь, что phone_number здесь есть!

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
        client_name=client_name,
        client_telegram_id=user.id,
        service_id=service_id,
        appointment_time=appointment_dt,
        client_phone=phone_number,  # <-- Номер телефона уже должен быть здесь
        google_event_id=None
    )

    appointment_id = await db.add_appointment(new_appointment)

    if appointment_id:
        await callback.message.edit_text(f"✅ Запись для клиента <b>{client_name}</b> успешно создана!\n\n"
                                         f"<b>Услуга:</b> {service_title}\n"
                                         f"<b>Время:</b> {date_str} {time_str}\n"
                                         f"<b>Телефон:</b> {phone_number}")  # Отображаем телефон в сообщении

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
        # --- Убедитесь, что phone_number передается здесь ---
        google_event_id = utils.google_calendar.create_google_calendar_event(
            appointment_time_str=f"{date_str} {time_str}",
            service_title=service_title,
            client_name=client_name,
            client_phone=phone_number,  # <-- Передаем номер телефона
            service_duration_minutes=service_duration
        )
        # --- КОНЕЦ ПРОВЕРКИ ---

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