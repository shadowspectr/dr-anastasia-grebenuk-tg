# main.py

import asyncio
import logging
import os
import signal
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler
# Импортируем функцию для запуска бота в отдельном потоке
from keep_alive import start_polling_in_thread # Предполагается, что эта функция существует в keep_alive.py

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# Глобальный обработчик ошибок
error_router = Router()

@error_router.errors()
async def error_handler(exception_update: types.ErrorEvent):
    """Обработчик ошибок для aiogram."""
    exception = exception_update.exception
    update = exception_update.update
    logger.error(f"Update: {update}")
    logger.error(f"Error: {exception}")

# --- Функции жизненного цикла приложения ---
# Теперь db будет доступен через dp.bot.my_data или dp.workflow_data
async def on_startup(dispatcher: Dispatcher):
    """Выполняется при старте бота."""
    logger.info("Starting bot and registering handlers...")

    # Получаем доступ к данным, переданным при создании Dispatcher или Bot
    db: Database = dispatcher.bot.my_data.get('db') # Получаем db из данных бота

    # Регистрируем роутеры
    dispatcher.include_router(error_router) # Обработчик ошибок должен быть первым
    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)

    # Инициализация и запуск планировщика, если база данных доступна
    if db:
        try:
            # Передаем бота и db в setup_scheduler
            scheduler = setup_scheduler(dispatcher.bot, db)
            scheduler.start()
            dispatcher["scheduler"] = scheduler
            logger.info("Scheduler started.")
        except Exception as e:
            logger.exception(f"Failed to start scheduler: {e}")
    else:
        logger.warning("Database not initialized, scheduler will not be started.")

    logger.info("Bot startup complete.")

async def on_shutdown(dispatcher: Dispatcher):
    """Выполняется при выключении бота."""
    logger.info("Shutting down bot...")
    # Корректное завершение работы планировщика
    if "scheduler" in dispatcher and dispatcher["scheduler"]:
        try:
            dispatcher["scheduler"].shutdown()
            logger.info("Scheduler shut down.")
        except Exception as e:
            logger.exception(f"Error shutting down scheduler: {e}")
    # Очистка FSM состояний (опционально)
    await dispatcher.storage.close()
    logger.info("Bot shutdown complete.")

# --- Основная функция запуска ---
def main():
    """Инициализирует бота и запускает его в режиме polling."""
    logger.info("Initializing bot components...")

    # ИНИЦИАЛИЗИРУЕМ DATABASE
    db = None # Инициализируем db как None
    try:
        db = Database(url=config.supabase_url, key=config.supabase_key)
        logger.info("Database connection established.")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        # db остается None, если инициализация не удалась

    # Инициализация хранилища состояний и диспетчера
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    # Настройка свойств бота (например, парсинг HTML)
    default_properties = DefaultBotProperties(parse_mode="HTML")

    # Создаем бота и передаем в него данные (db)
    bot = Bot(token=config.bot_token, default=default_properties, my_data={"db": db})

    # Регистрация обработчиков жизненного цикла
    # Теперь on_startup будет получать Dispatcher, из которого сможет достать бота и его данные
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot in polling mode...")

    # Запускаем бота в режиме polling в отдельном потоке
    # Передаем экземпляр диспетчера, бота и данные для бота
    start_polling_in_thread(dp, bot)

    logger.info("Bot polling started in a separate thread.")
    logger.info("Main process is now running to keep the bot alive.")

    # --- Поддержание активности основного процесса ---
    loop = asyncio.get_event_loop()

    def handle_signal(signum, frame):
        logger.info(f"Signal {signum} received. Shutting down...")
        # Для корректной остановки потока бота, нужно инициировать остановку dp
        # и подождать, пока цикл событий в потоке бота завершится.
        # Это может потребовать передачи события или объекта остановки.
        # Простейший вариант - остановить главный цикл, надеясь, что поток бота
        # завершится сам или будет убит.
        try:
            loop.stop()
        except RuntimeError:
            pass

    try:
        loop.add_signal_handler(signal.SIGINT, handle_signal, signal.SIGINT, None)
        loop.add_signal_handler(signal.SIGTERM, handle_signal, signal.SIGTERM, None)
    except NotImplementedError:
        logger.warning("Signal handlers for SIGINT/SIGTERM not available on this OS.")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Main process interrupted.")
    finally:
        logger.info("Cleaning up main process...")
        # Здесь также нужно убедиться, что поток бота корректно остановлен.
        # Если цикл главный остановлен, а поток бота работает, он может остаться висеть.
        # Возможно, потребуется менеджер потоков или другая синхронизация.
        logger.info("Main process finished.")

if __name__ == "__main__":
    main()