# main.py
import asyncio
import logging

from aiogram import Bot, Dispatcher, types, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage

# Импортируем наш keep_alive
import keep_alive

from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler  # <-- Раскомментируем планировщик

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# Глобальный обработчик ошибок
error_router = Router()


@error_router.errors()
async def error_handler(exception_update: types.ErrorEvent):
    update = exception_update.update
    exception = exception_update.exception
    logger.error(f"Критическая ошибка при обработке апдейта {update.update_id}")
    logger.exception(exception)
    try:
        # Убедитесь, что bot определен в этой области видимости
        await exception_update.update.bot.send_message(
            config.admin_id,
            f"<b>❗️ Произошла ошибка в боте!</b>\n"
            f"<b>Тип:</b> {type(exception).__name__}\n<b>Ошибка:</b> {exception}"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение об ошибке админу: {e}")
    return True


async def main():
    logger.info("Starting bot in polling mode...")

    # Инициализация
    db = Database(url=config.supabase_url, key=config.supabase_key)
    storage = MemoryStorage()
    default_properties = DefaultBotProperties(parse_mode="HTML")
    bot = Bot(token=config.bot_token, default=default_properties)
    dp = Dispatcher(storage=storage)

    # Регистрируем роутеры (обработчик ошибок первым)
    dp.include_router(error_router)
    dp.include_router(common_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(client_handlers.router)

    # Настраиваем и запускаем планировщик
    scheduler = setup_scheduler(bot, db)
    scheduler.start()

    # Удаляем старый вебхук, если он был
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        # Запускаем long polling
        await dp.start_polling(bot, db=db, scheduler=scheduler)
    finally:
        logger.info("Bot stopped.")
        if scheduler.running:
            scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    # Запускаем веб-сервер в отдельном потоке
    keep_alive.keep_alive()
    logger.info("Keep-alive server started.")

    # Запускаем основную асинхронную функцию бота
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot execution stopped by user.")