# keep_alive.py
import logging
import os
import asyncio
from aiogram import Bot, Dispatcher
from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler
from threading import Thread

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Функции бота ---
async def _run_bot_polling_with_context(dp: Dispatcher, bot: Bot, dispatcher_data: dict):
    """Внутренняя функция для запуска бота в режиме polling с контекстом."""
    logger.info("Bot polling task started.")
    try:
        # Передаем данные в диспетчер перед запуском
        # В aiogram v3, данные передаются через регистрируемые хендлеры или при создании Dispatcher.
        # Напрямую передать в start_polling нельзя.
        # Полагаемся на то, что dp уже инициализирован с нужными данными, или что on_startup
        # сможет получить их из глобального доступа (что не очень хорошо).
        # Более правильный способ: передать db при создании Dispatcher или через dp.data
        dp.data.update(dispatcher_data) # Добавляем данные в Dispatcher

        # Теперь регистрируем обработчики жизненного цикла, которые получат доступ к dp.data
        # В main.py мы уже регистрировали их, здесь они будут работать в другом контексте.
        # Перерегистрация здесь не нужна, если они уже были зарегистрированы до создания потока.

        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Bot polling task cancelled.")
    except Exception as e:
        logger.exception(f"An error occurred during bot polling: {e}")
    finally:
        # Очистка, если необходимо
        if dp:
            await dp.storage.close()
            logger.info("Storage closed.")
        logger.info("Bot polling task finished.")

def start_polling_in_thread(dp: Dispatcher, bot: Bot, dispatcher_data: dict):
    """Запускает бота в режиме polling в отдельном потоке с контекстом."""
    logger.info("Creating a new thread for bot polling.")
    # Создаем задачу для запуска бота с контекстом
    task = asyncio.ensure_future(_run_bot_polling_with_context(dp, bot, dispatcher_data))

    # Создаем поток для запуска цикла событий asyncio с нашей задачей
    thread = Thread(target=lambda t=task: asyncio.run(t))
    thread.daemon = True # Поток будет завершен, если основной процесс завершится
    thread.start()
    logger.info("Bot polling thread started.")
    return thread