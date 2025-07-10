import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    logger = logging.getLogger(__name__)
    logger.info("Starting bot...")

    db = Database(url=config.supabase_url, key=config.supabase_key)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Используем новый способ передачи parse_mode, чтобы не было предупреждений
    default_properties = DefaultBotProperties(parse_mode="HTML")

    # Создаем бота самым обычным способом. Никаких сессий, коннекторов и SSL-контекстов.
    bot = Bot(token=config.bot_token, default=default_properties)

    # Регистрация роутеров
    dp.include_router(common_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(client_handlers.router)

    scheduler = setup_scheduler(bot, db)
    scheduler.start()

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, db=db)
    finally:
        await bot.session.close()
        scheduler.shutdown()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by user.")