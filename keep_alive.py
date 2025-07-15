# keep_alive.py
import logging
import os
import asyncio
from aiogram import Bot, Dispatcher
from config_reader import config
from database.db_supabase import Database # Нужен для инициализации бота
from handlers import common_handlers, admin_handlers, client_handlers # Нужны для регистрации роутеров
from utils.scheduler import setup_scheduler # Нужен для инициализации бота
from threading import Thread

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Функции бота ---
async def _run_bot_polling(dp: Dispatcher, bot: Bot):
    """Внутренняя функция для запуска бота в режиме polling."""
    logger.info("Bot polling task started.")
    try:
        # Запуск обработчиков жизненного цикла
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Bot polling task cancelled.")
    except Exception as e:
        logger.exception(f"An error occurred during bot polling: {e}")
    finally:
        # Дополнительная очистка, если необходимо
        if dp:
            await dp.storage.close()
            logger.info("Storage closed.")
        logger.info("Bot polling task finished.")

def start_polling_in_thread(dp: Dispatcher, bot: Bot):
    """Запускает бота в режиме polling в отдельном потоке."""
    logger.info("Creating a new thread for bot polling.")
    # Создаем задачу для запуска бота
    task = asyncio.ensure_future(_run_bot_polling(dp, bot))

    # Создаем поток для запуска цикла событий asyncio с нашей задачей
    thread = Thread(target=lambda t=task: asyncio.run(t))
    thread.daemon = True # Поток будет завершен, если основной процесс завершится
    thread.start()
    logger.info("Bot polling thread started.")
    return thread # Возвращаем поток, если нужно будет им управлять