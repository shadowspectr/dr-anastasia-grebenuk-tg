# utils/notifications.py

import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from config_reader import config
from database.models import Appointment

logger = logging.getLogger(__name__)

async def notify_admin_on_new_appointment(bot: Bot, appointment: Appointment, service_title: str, phone_number: str):
    """
    Отправляет уведомление администратору о новой записи.
    """
    if not config.admin_id:
        logger.warning("ADMIN_ID не установлен. Невозможно отправить уведомление.")
        return

    appointment_time_str = appointment.appointment_time.strftime('%d.%m.%Y в %H:%M')

    text = (
        f"🔔 <b>Новая запись!</b>\n\n"
        f"👤 <b>Клиент:</b> {appointment.client_name}\n"
        f"✍️ <b>Услуга:</b> {service_title}\n\n"
        f"🗓️ <b>Дата и время:</b> {appointment_time_str}\n"
        f"📞 <b>Телефон для связи: {phone_number}</b>\n\n"  # <-- Добавили телефон
        f"<i>Telegram ID клиента:</i> <code>{appointment.client_telegram_id}</code>"
    )

    try:
        await bot.send_message(
            chat_id=config.admin_id,
            text=text,
        )
        logger.info(f"Уведомление о новой записи отправлено администратору {config.admin_id}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке уведомления администратору: {e}")