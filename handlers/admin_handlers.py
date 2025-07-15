from aiogram import Router, types, F
from config_reader import config
from datetime import datetime
from database.db_supabase import Database
from keyboards.admin_keyboards import *

router = Router()
router.message.filter(F.from_user.id == config.admin_id)
router.callback_query.filter(F.from_user.id == config.admin_id)


@router.callback_query(F.data == "admin_today")
async def admin_today_appointments(callback: types.CallbackQuery, db: Database):
    today = datetime.now()
    appointments = db.get_appointments_for_day(today)

    if not appointments:
        await callback.message.edit_text("📅 На сегодня активных записей нет.", reply_markup=get_admin_main_keyboard())
        return

    text = f"📅 <b>Записи на сегодня ({today.strftime('%d.%m.%Y')}):</b>\n\n"
    builder = InlineKeyboardBuilder()

    for app in appointments:
        text += f"▪️ {app.appointment_time.strftime('%H:%M')} - {app.client_name} ({app.service_title})\n"
        builder.add(types.InlineKeyboardButton(text=f"{app.appointment_time.strftime('%H:%M')} - {app.client_name}",
                                               callback_data=f"admin_app_{app.id}"))

    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("admin_app_"))
async def admin_appointment_details(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]
    app = db.get_appointment_by_id(app_id)
    if not app:
        await callback.answer("Запись не найдена!", show_alert=True)
        return

    text = (f"<b>Детали записи:</b>\n\n"
            f"<b>Клиент:</b> {app.client_name}\n"
            f"<b>Telegram ID:</b> {app.client_telegram_id}\n"
            f"<b>Услуга:</b> {app.service_title}\n"
            f"<b>Время:</b> {app.appointment_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"<b>Статус:</b> {app.status}")

    await callback.message.edit_text(text, reply_markup=get_admin_appointment_actions_keyboard(app.id))


# Обработчики действий с записью
@router.callback_query(F.data.startswith("admin_complete_"))
async def admin_complete(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]
    db.update_appointment_status(app_id, 'completed')
    await callback.answer("Статус изменен на 'Завершена'", show_alert=True)
    await admin_today_appointments(callback, db)


@router.callback_query(F.data.startswith("admin_cancel_"))
async def admin_cancel(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]
    db.update_appointment_status(app_id, 'cancelled')
    await callback.answer("Статус изменен на 'Отменена'", show_alert=True)
    await admin_today_appointments(callback, db)


@router.callback_query(F.data.startswith("admin_delete_"))
async def admin_delete(callback: types.CallbackQuery, db: Database):
    app_id = callback.data.split("_")[2]
    db.delete_appointment(app_id)
    await callback.answer("Запись удалена!", show_alert=True)
    await admin_today_appointments(callback, db)