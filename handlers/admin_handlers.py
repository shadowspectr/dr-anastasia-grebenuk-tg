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


# --- Обработчик кнопки "Записи на сегодня" ---
@router.callback_query(F.data == "admin_today")
async def admin_today_appointments(callback: types.CallbackQuery, db: Database):
    logger.info(f"Admin {callback.from_user.id} requested today's appointments.")
    today = datetime.now()
    appointments = await db.get_appointments_for_day(today)  # <-- await

    if not appointments:
        await callback.message.edit_text(
            "📅 На сегодня активных записей нет.",
            reply_markup=get_admin_main_keyboard()
        )
        return

    text = f"📅 <b>Записи на сегодня ({today.strftime('%d.%m.%Y')}):</b>\n\n"
    builder = InlineKeyboardBuilder()

    for app in appointments:
        client_name = app.client_name or "Имя не указано"
        service_title = app.service_title or "Услуга не указана"
        app_time = app.appointment_time.strftime('%H:%M') if app.appointment_time else "Время не указано"

        text += f"▪️ {app_time} - {client_name} ({service_title})\n"

        # Важно: Убедитесь, что app.id существует и является уникальным идентификатором записи
        builder.add(types.InlineKeyboardButton(
            text=f"{app_time} - {client_name}",
            callback_data=f"admin_app_{app.id}"
        ))

    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


# --- Обработчик для просмотра деталей конкретной записи ---
@router.callback_query(F.data.startswith("admin_app_"))
async def admin_appointment_details(callback: types.CallbackQuery, db: Database):
    # Извлекаем ID записи из callback_data
    try:
        app_id = callback.data.split("_")[2]
    except IndexError:
        logger.error(f"Could not parse appointment ID from callback data: {callback.data}")
        await callback.answer("Ошибка в формате данных.", show_alert=True)
        return

    logger.info(f"Admin requested details for appointment id: {app_id}")
    app = await db.get_appointment_by_id(app_id)  # <-- await

    if not app:
        await callback.answer("Запись не найдена! Возможно, она была удалена.", show_alert=True)
        # Попробуем обновить список, чтобы убрать "мертвые" кнопки
        await admin_today_appointments(callback, db)
        return

    # Формируем текст с деталями
    text = (
        f"<b>Детали записи:</b>\n\n"
        f"<b>ID записи:</b> `{app.id}`\n"  # Отобразим ID записи для удобства
        f"<b>Клиент:</b> {app.client_name}\n"
        f"<b>Telegram ID:</b> {app.client_telegram_id or 'Не указан'}\n"
        f"<b>Услуга:</b> {app.service_title}\n"
        f"<b>Время:</b> {app.appointment_time.strftime('%d.%m.%Y %H:%M') if app.appointment_time else 'Не указано'}\n"
        f"<b>Номер телефона:</b> {app.client_phone or 'Не указан'}\n"  # Добавляем номер телефона
        f"<b>Статус:</b> {app.status}\n"
        f"<b>Google Event ID:</b> `{app.google_event_id or 'Не указан'}`"  # Отображаем Google Event ID
    )

    await callback.message.edit_text(text, reply_markup=get_admin_appointment_actions_keyboard(app.id))


# --- Обработчики действий с записью ---

@router.callback_query(F.data.startswith("admin_complete_"))
async def admin_complete(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]

    # Обновляем статус записи в БД
    await db.update_appointment_status(app_id, 'completed')
    await callback.answer("Статус изменен на 'Завершена'", show_alert=True)

    # Возвращаемся к списку записей
    await admin_today_appointments(callback, db)


@router.callback_query(F.data.startswith("admin_cancel_"))
async def admin_cancel(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]

    # Обновляем статус записи в БД
    await db.update_appointment_status(app_id, 'cancelled')
    await callback.answer("Статус изменен на 'Отменена'", show_alert=True)

    # Возвращаемся к списку записей
    await admin_today_appointments(callback, db)


@router.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]

    # Удаляем запись из БД (и из Google Calendar, если это реализовано в delete_appointment)
    await db.delete_appointment(app_id)
    await callback.answer("Запись удалена!", show_alert=True)

    # Возвращаемся к списку записей
    await admin_today_appointments(callback, db)