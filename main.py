import logging
import os
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler

# --- Глобальные переменные ---
# Инициализируем все на верхнем уровне, чтобы они были доступны везде
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# Объекты, которые нужны для работы бота
db = Database(url=config.supabase_url, key=config.supabase_key)
storage = MemoryStorage()
default_properties = DefaultBotProperties(parse_mode="HTML")
bot = Bot(token=config.bot_token, default=default_properties)
dp = Dispatcher(storage=storage)

# Переменные для вебхука
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default-super-secret")
WEBHOOK_PATH = config.webhook_path
BASE_WEBHOOK_URL = config.web_server_url


async def on_startup(bot: Bot, dispatcher: Dispatcher):
    """
    Функция, выполняемая при старте приложения.
    Устанавливает вебхук и запускает планировщик.
    """
    logger.info("Configuring webhook...")
    await bot.set_webhook(
        url=f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}",
        secret_token=WEBHOOK_SECRET
    )

    logger.info("Starting scheduler...")
    scheduler = setup_scheduler(bot, db)
    scheduler.start()
    logger.info("Startup complete.")


async def on_shutdown(bot: Bot, dispatcher: Dispatcher):
    """

    Функция, выполняемая при завершении работы.
    """
    logger.info("Shutting down...")
    await bot.delete_webhook()
    # Планировщик остановится сам при завершении процесса
    logger.info("Shutdown complete.")


def setup_handlers(dispatcher: Dispatcher):
    """
    Регистрирует все роутеры.
    """
    logger.info("Configuring handlers...")
    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)


# --- Основная точка входа ---
if __name__ == "__main__":
    # 1. Регистрируем хэндлеры
    setup_handlers(dp)

    # 2. Регистрируем функции startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # 3. Создаем веб-приложение aiohttp
    app = web.Application()

    # 4. Создаем и регистрируем обработчик вебхуков
    webhook_request_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
        db=db  # Передаем db в каждый апдейт
    )
    webhook_request_handler.register(app, path=WEBHOOK_PATH)

    # 5. Передаем управление в aiogram для запуска
    setup_application(app, dp, bot=bot)

    # 6. Запускаем веб-сервер
    # host='0.0.0.0' - слушать на всех интерфейсах
    # port=10000 - порт, который слушает Render
    logger.info("Starting aiohttp server...")
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))