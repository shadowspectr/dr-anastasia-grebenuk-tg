# utils/notifications.py

import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from config_reader import config
from database.models import Appointment

logger = logging.getLogger(__name__)

async def notify_admin_on_new_appointment(bot: Bot, appointment: Appointment, service_title: str):
    """
    Отправляет уведомление администратору о новой записи.
    """
    if not config.admin_id:
        logger.warning("ADMIN_ID не установлен. Невозможно отправить уведомление.")
        return

    # Форматируем дату и время для красивого вывода
    appointment_time_str = appointment.appointment_time.strftime('%d.%m.%Y в %H:%M')

    text = (
        f"🔔 <b>Новая запись!</b>\n\n"
        f"👤 <b>Клиент:</b> {appointment.client_name}\n"
        f"✍️ <b>Услуга:</b> {service_title}\n\n"
        f"🗓️ <b>Дата и время:</b> {appointment_time_str}\n\n"
        f"<i>Telegram ID клиента:</i> <code>{appointment.client_telegram_id}</code>"
    )

    try:
        await bot.send_message(
            chat_id=config.admin_id,
            text=text,
            # Можно добавить инлайн-кнопку для быстрого перехода к записям на день
            # reply_markup=...
        )
        logger.info(f"Уведомление о новой записи отправлено администратору {config.admin_id}")
    except TelegramAPIError as e:
        logger.error(f"Не удалось отправить уведомление администратору {config.admin_id}: {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке уведомления администратору: {e}")