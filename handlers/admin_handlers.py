# handlers/admin_handlers.py

import logging
from aiogram import Bot, Router, types, F
from aiogram.fsm.context import FSMContext
from config_reader import config
from datetime import datetime
import pytz

from database.db_supabase import Database
from database.models import Appointment
from states.fsm_states import AdminStates
from keyboards.admin_keyboards import *
# Импортируем только клавиатуры выбора услуг, они все еще нужны
from keyboards.client_keyboards import (
    get_service_categories_keyboard,
    get_services_keyboard
)
from utils.google_calendar import GoogleCalendar

router = Router()
# Фильтр, чтобы эти хэндлеры работали только для админа
router.message.filter(F.from_user.id == config.admin_id)
router.callback_query.filter(F.from_user.id == config.admin_id)

logger = logging.getLogger(__name__)
TIMEZONE = pytz.timezone('Europe/Moscow')


# --- Логика просмотра и удаления записей (без изменений) ---
# ... (код для admin_today_appointments, admin_appointment_details, admin_delete_appointment) ...
@router.callback_query(F.data == "admin_today")
async def admin_today_appointments(callback: types.CallbackQuery, db: Database):
    logger.info("Admin requested today's appointments.")
    today = datetime.now(TIMEZONE)
    events = await GoogleCalendar.get_events_with_details(today)
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
        builder.add(types.InlineKeyboardButton(text=f"{event_start_time.strftime('%H:%M')} - {summary}",
                                               callback_data=f"admin_app_{event_id}"))
    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="🔙 В главное меню", callback_data="admin_back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin_app_"))
async def admin_appointment_details(callback: types.CallbackQuery):
    event_id = callback.data.split("_")[2]
    await callback.message.edit_text("Выберите действие для этой записи:",
                                     reply_markup=get_admin_appointment_actions_keyboard(event_id))


@router.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete_appointment(callback: types.CallbackQuery, db: Database):
    event_id = callback.data.split("_")[2]
    logger.info(f"Admin trying to delete event with google_id: {event_id}")
    deleted_from_google = await GoogleCalendar.delete_event(event_id)
    if deleted_from_google:
        await db.delete_appointment_by_google_id(event_id)
        await callback.answer("Запись успешно удалена!", show_alert=True)
        await admin_today_appointments(callback, db)
    else:
        await callback.answer("Не удалось удалить запись из Google Календаря.", show_alert=True)


# --- НОВАЯ ВЕТКА FSM С РУЧНЫМ ВВОДОМ ---

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


@router.callback_query(AdminStates.waiting_for_service, F.data.startswith("service_"))
async def admin_pick_service(callback: types.CallbackQuery, state: FSMContext, db: Database):
    service_id = callback.data.split("_")[1]
    service = await db.get_service_by_id(service_id)
    if not service:
        await callback.answer("Ошибка: не найдена услуга.", show_alert=True)
        return
    await state.update_data(service_id=service.id, service_title=service.title)
    # Запрашиваем ручной ввод даты
    await callback.message.edit_text("Теперь введите дату записи.\n\n"
                                     "<b>Подсказка:</b> используйте формат <b>ДД.ММ.ГГГГ</b> (например, 25.12.2024)")
    await state.set_state(AdminStates.waiting_for_date_input)


@router.message(AdminStates.waiting_for_date_input)
async def admin_enter_date(message: types.Message, state: FSMContext):
    try:
        # Проверяем, что дата введена в правильном формате
        date_obj = datetime.strptime(message.text, '%d.%m.%Y')
        await state.update_data(date=date_obj.strftime('%Y-%m-%d'))
        await message.answer("Отлично! Теперь введите время записи.\n\n"
                             "<b>Подсказка:</b> используйте формат <b>ЧЧ:ММ</b> (например, 14:00 или 09:30)")
        await state.set_state(AdminStates.waiting_for_time_input)
    except ValueError:
        await message.reply(
            "Неверный формат даты. Пожалуйста, введите дату в формате <b>ДД.ММ.ГГГГ</b> (например, 25.12.2024).")
        # Остаемся в том же состоянии, ожидая правильного ввода


@router.message(AdminStates.waiting_for_time_input)
async def admin_enter_time_and_book(message: types.Message, state: FSMContext, db: Database, bot: Bot):
    time_str = message.text
    try:
        # Проверяем формат времени
        datetime.strptime(time_str, '%H:%M')
    except ValueError:
        await message.reply(
            "Неверный формат времени. Пожалуйста, введите время в формате <b>ЧЧ:ММ</b> (например, 14:00).")
        return

    await message.answer("Минутку, проверяю и создаю запись...")
    data = await state.get_data()

    naive_dt = datetime.strptime(f"{data['date']} {time_str}", '%Y-%m-%d %H:%M')
    appointment_dt = TIMEZONE.localize(naive_dt)

    # Финальная проверка занятости
    current_busy_slots = await GoogleCalendar.get_busy_slots(appointment_dt)
    is_slot_taken = any(
        slot.astimezone(TIMEZONE).time().hour == appointment_dt.time().hour for slot in current_busy_slots)

    if is_slot_taken:
        await message.answer("Это время уже занято. Пожалуйста, начните сначала или введите другое время.")
        # Можно остаться в состоянии waiting_for_time_input, чтобы дать админу еще попытку
        return

    # Создаем событие
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
        await message.answer("✅ Запись успешно создана!")
    else:
        await message.answer("❌ Не удалось создать запись в календаре.")

    await state.clear()


# Возврат в главное меню админа
@router.callback_query(F.data == "admin_back_main")
async def admin_back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Добро пожаловать, Администратор!",
        reply_markup=get_admin_main_keyboard()
    )