import logging
from aiogram import Router, types, F, Bot # <-- Добавляем Bot в импорты
from aiogram.fsm.context import FSMContext
from datetime import datetime
from database.db_supabase import Database
from database.models import Appointment
from states.fsm_states import ClientStates
from keyboards.client_keyboards import *
from utils.notifications import notify_admin_on_new_booking # <-- НОВЫЙ ИМПОРN
from utils.google_calendar import create_google_calendar_event

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


# Шаг 6: Подтверждение
@router.callback_query(ClientStates.waiting_for_confirmation, F.data == "confirm_booking")
async def client_confirm_booking(callback: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data()
    user = callback.from_user

    appointment_dt = datetime.strptime(f"{data['date']} {data['time']}", '%Y-%m-%d %H:%M')

    new_appointment = Appointment(
        client_name=user.full_name,
        client_telegram_id=user.id,
        service_id=data['service_id'],
        appointment_time=appointment_dt
    )

    appointment_id = await db.add_appointment(new_appointment)

    if appointment_id:
        # Успешно записались, отправляем подтверждение клиенту
        await callback.message.edit_text(
            "✅ Вы успешно записаны!\n\n"
            "Вам придет напоминание за день до визита. Ждем вас!"
        )

        # --- ОТПРАВКА УВЕДОМЛЕНИЯ АДМИНИСТРАТОРУ ---
        new_appointment.id = appointment_id
        await notify_admin_on_new_booking(
            bot=bot,
            appointment=new_appointment,
            service_title=data['service_title'],
            service_price=data['service_price']
        )
        # --------------------------------------------

        # --- ИНТЕГРАЦИЯ С GOOGLE CALENDAR ---
        # Получаем длительность услуги из БД, если это возможно, или используем значение по умолчанию
        service_duration = await db.get_service_duration(data['service_id']) # Предполагаем, что такой метод есть в db
        if not service_duration:
             service_duration = 60 # Значение по умолчанию, если нет информации о длительности

        if create_google_calendar_event(
            appointment_time_str=f"{data['date']} {data['time']}",
            service_title=data['service_title'],
            client_name=user.full_name,
            service_duration_minutes=service_duration
        ):
            logger.info(f"Событие для клиента {user.id} успешно добавлено в Google Calendar.")
        else:
            logger.warning(f"Не удалось добавить событие для клиента {user.id} в Google Calendar.")
        # ------------------------------------

    else:
        # Если произошла ошибка при записи
        await callback.message.edit_text("❌ Произошла ошибка при записи. Попробуйте позже.")

    await state.clear()


# Отмена на любом этапе
@router.callback_query(F.data == "cancel_booking")
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    # Эта клавиатура не делает запросов в БД, поэтому await не нужен
    await callback.message.edit_text("Запись отменена.", reply_markup=get_client_main_keyboard())