# handlers/admin_handlers.py

import logging
from aiogram import Router, types, F, Bot
from config_reader import config
from datetime import datetime
from database.db_supabase import Database
from keyboards.admin_keyboards import *
from keyboards.client_keyboards import *
from states.fsm_states import AdminStates
from aiogram.fsm.context import FSMContext
from database.models import Appointment
from utils.notifications import notify_admin_on_new_booking
import utils.google_calendar
import utils.gemini_api


router = Router()
# Фильтр, чтобы эти хэндлеры работали только для админа
router.message.filter(F.from_user.id == config.admin_id)
router.callback_query.filter(F.from_user.id == config.admin_id)

logger = logging.getLogger(__name__)


# --- Обработчик кнопки "Нейросеть" ---
@router.callback_query(F.data == "admin_gemini_chat")
async def admin_gemini_start_chat(callback: types.CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} wants to use Gemini AI.")

    await state.set_state(AdminStates.waiting_for_gemini_prompt)
    # --- ИСПРАВЛЕНИЕ: Используем parse_mode='HTML' ---
    await callback.message.edit_text("Привет! Я твой помощник Gemini.\n"
                                     "Задай мне вопрос или дай задание. Чтобы выйти из чата, отправь /cancel.\n\n"
                                     "<b>Что ты хочешь сделать?</b>", parse_mode='HTML')  # <-- Добавлено
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---


# --- Обработчик для получения запроса от админа ---
@router.message(AdminStates.waiting_for_gemini_prompt)
async def admin_gemini_prompt(message: types.Message, state: FSMContext, bot: Bot):
    user_prompt = message.text

    if user_prompt.lower() == '/cancel':
        await state.finish()
        await message.answer("Диалог с нейросетью завершен.", reply_markup=get_admin_main_keyboard())
        return

    # Сохраняем ID сообщения, чтобы его можно было отредактировать/удалить
    await state.update_data(last_message_id=message.message_id)

    # Показываем, что бот "думает"
    processing_message = await message.answer("🧠 Обрабатываю ваш запрос...")

    # Отправляем запрос к Gemini API
    response_parts = await utils.gemini_api.generate_text(user_prompt)

    # Удаляем "обрабатывающее" сообщение
    await bot.delete_message(chat_id=message.chat.id, message_id=processing_message.message_id)

    if response_parts:  # Если получили список ответов
        for part in response_parts:
            if part:  # Отправляем только непустые части
                # --- ИСПРАВЛЕНИЕ: Используем parse_mode='HTML' ---
                await message.answer(part, parse_mode='HTML')  # <-- Добавлено parse_mode
                # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
    else:
        await message.answer("❌ Не удалось получить ответ от нейросети. Попробуйте позже.")

    # Остаемся в том же состоянии, чтобы админ мог продолжить диалог
    await state.set_state(AdminStates.waiting_for_gemini_prompt)


# --- Обработчик отмены диалога с Gemini ---
@router.message(AdminStates.waiting_for_gemini_prompt, F.text.lower() == "/cancel")
async def cancel_gemini_chat(message: types.Message, state: FSMContext):
    await state.finish()


# --- Обработчик кнопки "Записать клиента" ---
@router.callback_query(F.data == "admin_book_client")
async def admin_start_booking_client(callback: types.CallbackQuery, state: FSMContext, db: Database):
    logger.info(f"Admin {callback.from_user.id} wants to book a client.")
    await state.set_state(AdminStates.waiting_for_client_name)
    await callback.message.edit_text("Пожалуйста, введите имя клиента:")


# --- Шаг 1: Ввод имени клиента ---
@router.message(AdminStates.waiting_for_client_name)
async def admin_get_client_name(message: types.Message, state: FSMContext, db: Database):
    client_name = message.text
    await state.update_data(client_name=client_name)

    keyboard = await get_service_categories_keyboard(db)
    await message.answer("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_category)


# --- Шаг 2: Выбор категории (для админа) ---
@router.callback_query(AdminStates.waiting_for_category, F.data.startswith("category_"))
async def admin_pick_category(callback: types.CallbackQuery, state: FSMContext, db: Database):
    category_id = callback.data.split("_")[1]
    await state.update_data(category_id=category_id)
    keyboard = await get_services_keyboard(db, category_id)
    await callback.message.edit_text("Теперь выберите услугу:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_service)


# --- Обработчик возврата от выбора услуг к категориям (для админа) ---
@router.callback_query(AdminStates.waiting_for_service, F.data == "back_to_category_choice")
async def admin_back_to_category_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
    await state.update_data(service_id=None, service_title=None, service_price=None)

    keyboard = await get_service_categories_keyboard(db)
    await callback.message.edit_text("Выберите категорию услуг:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_category)


# --- Шаг 3: Выбор услуги (для админа) ---
@router.callback_query(AdminStates.waiting_for_service, F.data.startswith("service_"))
async def admin_pick_service(callback: types.CallbackQuery, state: FSMContext, db: Database):
    service_id = callback.data.split("_")[1]
    service = await db.get_service_by_id(service_id)

    if not service:
        await callback.answer("Услуга не найдена, попробуйте снова.", show_alert=True)
        return

    await state.update_data(service_id=service_id, service_title=service.title, service_price=service.price)
    keyboard = await get_date_keyboard(db)
    await callback.message.edit_text(f"Вы выбрали: {service.title}.\nТеперь выберите удобный день:",
                                     reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_date)


# --- Обработчик возврата от выбора времени к выбору даты (для админа) ---
@router.callback_query(AdminStates.waiting_for_time, F.data == "back_to_date_choice")
async def admin_back_to_date_choice(callback: types.CallbackQuery, state: FSMContext, db: Database):
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
    await state.set_state(AdminStates.waiting_for_time)


# --- Шаг 4: Выбор даты (для админа) ---
@router.callback_query(AdminStates.waiting_for_date, F.data.startswith("date_"))
async def admin_pick_date(callback: types.CallbackQuery, state: FSMContext, db: Database):
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    keyboard = await get_time_slots_keyboard(target_date, db)
    await callback.message.edit_text(f"Выбрана дата: {date_str}.\nТеперь выберите свободное время:",
                                     reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_time)


# --- Шаг 5: Выбор времени (для админа) ---
@router.callback_query(AdminStates.waiting_for_time, F.data.startswith("time_"))
async def admin_pick_time(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.split("_")[1]
    await state.update_data(time=time_str)

    data = await state.get_data()

    # --- НАЧАЛО ИЗМЕНЕНИЙ: Запрашиваем номер ТЕЛЕФОНА после выбора времени ---
    await state.set_state(AdminStates.waiting_for_phone)  # Переходим в состояние ожидания номера
    await callback.message.edit_text(
        "Отлично! Теперь, пожалуйста, укажите ваш контактный номер телефона (например, +79991234567).")


# --- Шаг 6: Получение номера телефона ---
# Этот обработчик срабатывает, когда администратор вводит номер телефона
@router.message(AdminStates.waiting_for_phone)
async def admin_provide_phone_number(message: types.Message, state: FSMContext, db: Database, bot: Bot):
    phone_number = message.text
    await state.update_data(phone_number=phone_number)  # Сохраняем номер телефона

    data = await state.get_data()

    # Теперь, когда у нас есть ВСЕ данные, показываем финальное подтверждение
    text = (f"<b>Пожалуйста, проверьте детали вашей записи:</b>\n\n"
            f"<b>Клиент:</b> {data.get('client_name', 'Не указано')}\n"
            f"<b>Услуга:</b> {data.get('service_title', 'Не указано')}\n"
            f"<b>Стоимость:</b> {data.get('service_price', 'Не указано')} ₽\n"
            f"<b>Дата:</b> {data.get('date', 'Не указано')}\n"
            f"<b>Время:</b> {data.get('time', 'Не указано')}\n"
            f"<b>Номер телефона:</b> {phone_number}")

    # Отправляем новое сообщение с кнопками подтверждения/отмены
    await message.answer(text, reply_markup=get_confirmation_keyboard())
    await state.set_state(AdminStates.waiting_for_confirmation)  # Переходим в состояние финального подтверждения


# --- Шаг 7: Финальное подтверждение записи (после ввода номера) ---
@router.callback_query(AdminStates.waiting_for_confirmation, F.data == "confirm_booking")
async def admin_confirm_booking(callback: types.CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data()

    client_name = data.get('client_name')
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
        client_name=client_name,
        service_id=service_id,
        appointment_time=appointment_dt,
        client_phone=phone_number,
        google_event_id=None
    )

    appointment_id = await db.add_appointment(new_appointment)

    if appointment_id:
        await callback.message.edit_text(f"✅ Запись для клиента <b>{client_name}</b> успешно создана!\n\n"
                                         f"<b>Услуга:</b> {service_title}\n"
                                         f"<b>Время:</b> {date_str} {time_str}\n"
                                         f"<b>Телефон:</b> {phone_number}")

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
            logger.info(
                f"Событие Google Calendar с ID '{google_event_id}' успешно создано для записи '{appointment_id}'.")
            if await db.update_appointment_google_id(appointment_id, google_event_id):
                logger.info(f"Google Event ID '{google_event_id}' успешно сохранен для записи '{appointment_id}'.")
            else:
                logger.warning(
                    f"Не удалось сохранить Google Event ID '{google_event_id}' для записи '{appointment_id}'.")
        else:
            logger.warning(f"Не удалось создать событие Google Calendar для записи '{appointment_id}'.")
        # ------------------------------------

    else:
        await callback.message.edit_text("❌ Произошла ошибка при создании записи. Попробуйте позже.")

    await state.clear()


# --- Отмена операции админом ---
@router.callback_query(F.data == "cancel_admin_operation")
async def cancel_admin_operation(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Операция отменена.", reply_markup=get_admin_main_keyboard())



# --- Вспомогательная функция для проверки изменений ---
def should_edit_message(current_text: str, new_text: str, current_markup, new_markup):
    """
    Проверяет, нужно ли редактировать сообщение.
    Возвращает True, если изменения есть, иначе False.
    """
    if current_text != new_text:
        return True
    if current_markup != new_markup:
        return True
    return False


# --- Обработчик кнопки "Записи на сегодня" ---
@router.callback_query(F.data == "admin_today")
async def admin_today_appointments(callback: types.CallbackQuery, db: Database):
    logger.info(f"Admin {callback.from_user.id} requested today's appointments.")
    today = datetime.now()
    appointments = await db.get_appointments_for_day(today)

    if not appointments:
        new_text = "📅 На сегодня активных записей нет."
        new_markup = get_admin_main_keyboard()
        # Проверяем, нужно ли редактировать
        if should_edit_message(callback.message.text, new_text, callback.message.reply_markup, new_markup):
            await callback.message.edit_text(new_text, reply_markup=new_markup)
        else:
            logger.info("Message for 'no appointments today' is already the same. Skipping edit.")
        return

    text_lines = [f"📅 <b>Записи на сегодня ({today.strftime('%d.%m.%Y')}):</b>\n\n"]
    builder = InlineKeyboardBuilder()

    for app in appointments:
        client_name = app.client_name or "Имя не указано"
        service_title = app.service_title or "Услуга не указана"
        app_time = app.appointment_time.strftime('%H:%M') if app.appointment_time else "Время не указано"

        text_lines.append(f"▪️ {app_time} - {client_name} ({service_title})\n")

        # Проверяем, что app.id существует
        if app.id:
            builder.add(types.InlineKeyboardButton(
                text=f"{app_time} - {client_name}",
                callback_data=f"admin_app_{app.id}"
            ))
        else:
            logger.warning(f"Appointment object is missing 'id' for an item: {app}")

    builder.adjust(1)
    new_text = "".join(text_lines)
    new_markup = builder.as_markup()

    # Проверяем, нужно ли редактировать
    if should_edit_message(callback.message.text, new_text, callback.message.reply_markup, new_markup):
        await callback.message.edit_text(new_text, reply_markup=new_markup)
    else:
        logger.info("Message for 'today appointments' is already the same. Skipping edit.")


# --- Обработчик для просмотра деталей конкретной записи ---
@router.callback_query(F.data.startswith("admin_app_"))
async def admin_appointment_details(callback: types.CallbackQuery, db: Database):
    try:
        app_id = callback.data.split("_")[2]
    except IndexError:
        logger.error(f"Could not parse appointment ID from callback data: {callback.data}")
        await callback.answer("Ошибка в формате данных.", show_alert=True)
        return

    logger.info(f"Admin requested details for appointment id: {app_id}")
    app = await db.get_appointment_by_id(app_id)

    if not app:
        logger.warning(f"Appointment with ID {app_id} not found for details request.")
        await callback.answer("Запись не найдена! Возможно, она была удалена.", show_alert=True)
        # Пытаемся обновить список, чтобы убрать "мертвые" кнопки
        # Проверяем, нужно ли редактировать, прежде чем вызывать admin_today_appointments
        # (чтобы избежать рекурсивной ошибки, если список пуст)
        # В данном случае, лучше просто сообщить пользователю, и пусть он сам обновит.
        # Или, можно сделать отдельный хэндлер для обновления списка.
        # Пока что просто оставим ответ пользователю.
        # Если вы хотите, чтобы он обновлял список, нужно более сложная логика проверки.
        # await admin_today_appointments(callback, db) # Это может вызвать ту же ошибку, если msg не изменился
        return  # Просто выходим, если запись не найдена.

    # Формируем текст с деталями
    text_parts = [
        f"<b>Детали записи:</b>\n\n",
        f"<b>ID записи:</b> `{app.id}`\n",
        f"<b>Клиент:</b> {app.client_name}\n",
        f"<b>Telegram ID:</b> {app.client_telegram_id or 'Не указан'}\n",
        f"<b>Услуга:</b> {app.service_title}\n",
        f"<b>Время:</b> {app.appointment_time.strftime('%d.%m.%Y %H:%M') if app.appointment_time else 'Не указано'}\n",
        f"<b>Номер телефона:</b> {app.client_phone or 'Не указан'}\n",
        f"<b>Статус:</b> {app.status}\n",
        f"<b>Google Event ID:</b> `{app.google_event_id or 'Не указан'}`"
    ]
    new_text = "".join(text_parts)
    new_markup = get_admin_appointment_actions_keyboard(app.id)

    # Проверяем, нужно ли редактировать
    if should_edit_message(callback.message.text, new_text, callback.message.reply_markup, new_markup):
        await callback.message.edit_text(new_text, reply_markup=new_markup)
    else:
        logger.info(f"Message for appointment details {app.id} is already the same. Skipping edit.")


# --- Обработчики действий с записью ---

@router.callback_query(F.data.startswith("admin_complete_"))
async def admin_complete(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]

    # Обновляем статус записи в БД
    await db.update_appointment_status(app_id, 'completed')
    await callback.answer("Статус изменен на 'Завершена'", show_alert=True)

    # Возвращаемся к списку, но только если нужно его обновить
    # Если список не изменился, edit_text будет проигнорирован
    await admin_today_appointments(callback, db)  # <-- Здесь тоже может быть проблема, если список не изменился


@router.callback_query(F.data.startswith("admin_cancel_"))
async def admin_cancel(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]

    # Обновляем статус записи в БД
    await db.update_appointment_status(app_id, 'cancelled')
    await callback.answer("Статус изменен на 'Отменена'", show_alert=True)

    # Возвращаемся к списку
    await admin_today_appointments(callback, db)  # <-- Здесь тоже может быть проблема


@router.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]

    # Удаляем запись из БД (и из Google Calendar, если это реализовано в delete_appointment)
    await db.delete_appointment(app_id)
    await callback.answer("Запись удалена!", show_alert=True)

    # Возвращаемся к списку
    await admin_today_appointments(callback, db)  # <-- Здесь тоже может быть проблема