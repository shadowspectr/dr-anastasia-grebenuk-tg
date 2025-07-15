# keep_alive.py
import logging
import os
import asyncio
from aiogram import Bot, Dispatcher, Router # Импортируем Router
from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler
from threading import Thread


# Импортируем error_router из main.py
# Это может потребовать настройки PYTHONPATH или структуры проекта
# Если main.py является частью пакета, то: from .main import error_router
# Если main.py запускается как скрипт, импорт может быть сложнее.
# Проще всего перенести error_router в отдельный файл, например, `error_handler.py`
# и импортировать его везде.
# Для простоты предположим, что мы можем его импортировать так:
try:
    from main import error_router # <<< Импортируем error_router
except ImportError:
    logger.error("Could not import error_router from main.py. Please ensure it's accessible.")
    error_router = Router() # Создаем пустой, чтобы избежать дальнейших ошибок импорта

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Функции бота ---
async def _run_bot_polling_task(dp: Dispatcher, bot: Bot):
    """Внутренняя функция для запуска бота в режиме polling."""
    logger.info("Bot polling task started.")
    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Bot polling task cancelled.")
    except Exception as e:
        logger.exception(f"An error occurred during bot polling: {e}")
    finally:
        if dp:
            await dp.storage.close()
            logger.info("Storage closed.")
        logger.info("Bot polling task finished.")

def start_polling_in_thread(dp: Dispatcher, bot: Bot):
    """Запускает бота в режиме polling в отдельном потоке."""
    logger.info("Creating a new thread for bot polling.")

    # Теперь on_startup будет вызываться здесь и получит dp
    # Регистрируем обработчики жизненного цикла
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Создаем цикл событий и задачу
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(_run_bot_polling_task(dp, bot))

    # Создаем поток, который будет запускать этот цикл событий
    thread = Thread(target=lambda l=loop, t=task: l.run_until_complete(t))
    thread.daemon = True
    thread.start()
    logger.info("Bot polling thread started.")
    return thread

# --- Обработчики жизненного цикла (определены здесь для использования в потоке) ---
async def on_startup(dispatcher: Dispatcher):
    """Выполняется при старте бота."""
    logger.info("Bot startup hook called in thread.")
    bot: Bot = dispatcher.bot
    db = bot.my_data.get('db')

    # Регистрируем роутеры
    dispatcher.include_router(error_router) # Используем импортированный error_router
    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)

    if db:
        try:
            scheduler = setup_scheduler(bot, db)
            scheduler.start()
            dispatcher["scheduler"] = scheduler
            logger.info("Scheduler started in thread.")
        except Exception as e:
            logger.exception(f"Failed to start scheduler in thread: {e}")
    else:
        logger.warning("Database not initialized in thread, scheduler will not be started.")

    logger.info("Bot startup complete in thread.")

async def on_shutdown(dispatcher: Dispatcher):
    """Выполняется при выключении бота."""
    logger.info("Bot shutdown hook called in thread.")
    if "scheduler" in dispatcher and dispatcher["scheduler"]:
        try:
            dispatcher["scheduler"].shutdown()
            logger.info("Scheduler shut down in thread.")
        except Exception as e:
            logger.exception(f"Error shutting down scheduler in thread: {e}")
    await dispatcher.storage.close()
    logger.info("Bot shutdown complete in thread.")