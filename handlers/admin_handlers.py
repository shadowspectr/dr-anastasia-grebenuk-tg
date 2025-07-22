# handlers/admin_handlers.py

import logging
from aiogram import Router, types, F, Bot
from config_reader import config
from datetime import datetime
from database.db_supabase import Database
from keyboards.admin_keyboards import *

router = Router()
# Фильтр, чтобы эти хэндлеры работали только для админа
router.message.filter(F.from_user.id == config.admin_id)
router.callback_query.filter(F.from_user.id == config.admin_id)

logger = logging.getLogger(__name__)


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