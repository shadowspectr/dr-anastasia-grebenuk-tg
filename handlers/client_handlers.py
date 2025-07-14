import logging
# Добавляем 'Bot' в эту строку импорта
from aiogram import Bot, Router, types, F
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database.db_supabase import Database
from database.models import Appointment
from states.fsm_states import ClientStates
from keyboards.client_keyboards import *
from utils.google_calendar import GoogleCalendar
# Исправляем имя импортируемой функции для соответствия
from utils.notifications import notify_admin_on_new_appointment

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


# Шаг 3: Выбор услуги
@router.callback_query(ClientStates.waiting_for_service, F.data.startswith("service_"))
async def client_pick_service(callback: types.CallbackQuery, state: FSMContext, db: Database):
    service_id = callback.data.split("_")[1]
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
async def client_pick_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)
    target_date = datetime.strptime(date_str, '%Y-%m-%d')

    # Получаем занятые слоты из Google Calendar
    busy_slots = await GoogleCalendar.get_busy_slots(target_date)
    # Генерируем клавиатуру времени на основе занятых слотов
    keyboard = get_time_slots_keyboard(target_date, busy_slots)

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


# Шаг 6: Подтверждение (обновленная логика)
@router.callback_query(ClientStates.waiting_for_confirmation, F.data == "confirm_booking")
async def client_confirm_booking(callback: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    await callback.answer("Минутку, создаю запись...")
    data = await state.get_data()
    user = callback.from_user
    appointment_dt = datetime.strptime(f"{data['date']} {data['time']}", '%Y-%m-%d %H:%M')

    # 1. Создаем событие в Google Calendar
    logger.info("Attempting to create event in Google Calendar...")
    google_event_id = await GoogleCalendar.add_appointment(
        client_name=user.full_name,
        service_title=data['service_title'],
        appointment_time=appointment_dt
    )

    # 2. Если в календаре создалось, сохраняем в БД и отправляем уведомление
    if google_event_id:
        logger.info(f"Google Calendar event created: {google_event_id}. Saving to DB...")
        new_appointment = Appointment(
            client_name=user.full_name,
            client_telegram_id=user.id,
            service_id=data['service_id'],
            appointment_time=appointment_dt
        )
        # Сохраняем в нашу БД Supabase
        db_appointment_id = await db.add_appointment(new_appointment)

        if db_appointment_id:
            logger.info(f"Appointment saved to DB with ID: {db_appointment_id}")
            # 3. Отправляем уведомление админу
            # Исправляем имя вызываемой функции
            await notify_admin_on_new_appointment(bot, new_appointment, data['service_title'])
            await callback.message.edit_text(
                "✅ Вы успешно записаны!\nЗапись добавлена в календарь и нашу систему."
            )
        else:
            # Случай, когда в календаре создалось, а в БД - нет.
            logger.error("Failed to save appointment to DB after creating it in Google Calendar.")
            await callback.message.edit_text(
                "❌ Произошла ошибка при сохранении записи в нашу систему. Пожалуйста, свяжитесь с администратором.")
    else:
        # Если даже в календаре не создалось
        logger.error("Failed to create event in Google Calendar.")
        await callback.message.edit_text(
            "❌ Произошла ошибка при записи в календарь. Свободное время могло измениться. Попробуйте снова.")

    await state.clear()


# Отмена на любом этапе
@router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Запись отменена.", reply_markup=get_client_main_keyboard())