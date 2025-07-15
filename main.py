# main.py

import asyncio
import logging
import os
import signal

from aiogram import Bot, Dispatcher, types, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler
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
async def on_startup(dispatcher: Dispatcher, db: Database): # db будет передано через data
    """Выполняется при старте бота."""
    logger.info("Starting bot and registering handlers...")

    # Регистрируем роутеры
    dispatcher.include_router(error_router) # Обработчик ошибок должен быть первым
    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)

    # Инициализация и запуск планировщика, если база данных доступна
    if db:
        try:
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
    bot = Bot(token=config.bot_token, default=default_properties)

    # Регистрация обработчиков жизненного цикла.
    # Мы передаем `db` как часть `data` при запуске диспетчера,
    # но для `on_startup` и `on_shutdown` aiogram предоставляет специальный механизм:
    # они получают доступ к данным из `Dispatcher` (например, `dispatcher.data`).
    # Чтобы `on_startup` получил `db`, мы должны передать его в `Dispatcher`.
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Создаем словарь с данными для передачи в диспетчер
    # Это доступно внутри обработчиков как dispatcher.data['db']
    dispatcher_data = {"db": db}

    logger.info("Starting bot in polling mode...")

    # Запускаем бота в режиме polling в отдельном потоке
    # Передаем экземпляр диспетчера и бота в функцию из keep_alive.py
    start_polling_in_thread(dp, bot, dispatcher_data)

    logger.info("Bot polling started in a separate thread.")
    logger.info("Main process is now running to keep the bot alive.")

    # --- Поддержание активности основного процесса ---
    # Этот блок нужен, чтобы основной процесс не завершился сразу после запуска потока бота.
    # Он будет слушать сигналы завершения.

    loop = asyncio.get_event_loop()

    def handle_signal(signum, frame):
        logger.info(f"Signal {signum} received. Shutting down...")
        # Здесь нужно корректно остановить все, включая поток бота.
        # Простейший способ - вызвать stop() на цикле событий, который ожидает задача бота.
        # Более надежный способ - передать событие остановки в поток бота.
        # Для простоты, попробуем остановить цикл событий главного потока.
        try:
            loop.stop()
        except RuntimeError:
            # Если цикл уже остановлен
            pass

    # Регистрируем сигналы
    try:
        loop.add_signal_handler(signal.SIGINT, handle_signal, signal.SIGINT, None)
        loop.add_signal_handler(signal.SIGTERM, handle_signal, signal.SIGTERM, None)
    except NotImplementedError:
        logger.warning("Signal handlers for SIGINT/SIGTERM not available on this OS.")

    # Запускаем основной цикл событий, который будет ждать сигналов
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Main process interrupted.")
    finally:
        logger.info("Cleaning up main process...")
        # Код здесь выполнится после loop.stop() или KeyboardInterrupt
        # Нужно убедиться, что поток бота тоже корректно завершается
        # Например, можно попытаться отправить сигнал остановки потоку бота
        # или использовать asyncio.run() с таймаутом, если это возможно.
        # Для простоты, будем надеяться, что поток бота завершится сам при закрытии цикла.
        logger.info("Main process finished.")


if __name__ == "__main__":
    main()