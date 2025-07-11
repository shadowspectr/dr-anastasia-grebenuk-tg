# utils/scheduler.py

import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.db_supabase import Database

logger = logging.getLogger(__name__)


async def send_reminders(bot: Bot, db: Database):
    """
    Асинхронная задача для отправки напоминаний о записях на завтра.
    """
    logger.info("Scheduler job: Checking for reminders...")

    # Используем await, так как метод DB теперь асинхронный
    appointments_to_remind = await db.get_upcoming_appointments_to_remind()

    if not appointments_to_remind:
        logger.info("No appointments for tomorrow to remind about.")
        return

    sent_count = 0
    for app in appointments_to_remind:
        if app.client_telegram_id:
            try:
                # Формируем текст сообщения
                text = (
                    f"🔔 <b>Напоминание о записи</b>\n\n"
                    f"Здравствуйте, {app.client_name}! Напоминаем, что вы записаны к нам завтра.\n\n"
                    f"<b>Услуга:</b> {app.service_title}\n"
                    f"<b>Время:</b> {app.appointment_time.strftime('%d.%m.%Y в %H:%M')}\n\n"
                    f"Ждем вас!"
                )

                # Отправляем сообщение
                await bot.send_message(app.client_telegram_id, text)

                # Помечаем, что напоминание отправлено (тоже асинхронно)
                await db.mark_as_reminded(app.id)

                sent_count += 1
                logger.info(f"Sent reminder for appointment ID {app.id} to user {app.client_telegram_id}")
            except Exception as e:
                logger.error(f"Failed to send reminder for appointment ID {app.id}: {e}")

    logger.info(f"Reminder job finished. Sent {sent_count} reminders.")


def setup_scheduler(bot: Bot, db: Database) -> AsyncIOScheduler:
    """
    Настраивает и возвращает экземпляр планировщика.
    """
    # Указываем часовой пояс, чтобы задача выполнялась в правильное время
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Добавляем задачу, которая будет выполняться каждый день в 19:00
    scheduler.add_job(send_reminders, 'cron', hour=19, minute=0, args=(bot, db))

    logger.info("Scheduler configured. Job 'send_reminders' will run daily at 19:00 (Europe/Moscow).")

    return scheduler