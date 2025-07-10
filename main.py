import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler

# --- Инициализация ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

db = Database(url=config.supabase_url, key=config.supabase_key)
storage = MemoryStorage()
default_properties = DefaultBotProperties(parse_mode="HTML")

bot = Bot(token=config.bot_token, default=default_properties)
dp = Dispatcher(storage=storage)

# --- Переменные для вебхука ---
# Лучше вынести секрет в переменные окружения для безопасности
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default-super-secret")
WEBHOOK_URL = f"{config.web_server_url}{config.webhook_path}"


# --- Функции жизненного цикла ---
async def on_startup(dispatcher: Dispatcher, bot: Bot):
    logger.info("Starting bot and setting webhook...")
    await bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET)

    # Роутеры теперь регистрируются здесь
    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)

    scheduler = setup_scheduler(bot, db)
    scheduler.start()

    logger.info("Bot started and webhook is set.")


async def on_shutdown(dispatcher: Dispatcher, bot: Bot):
    logger.info("Shutting down bot and deleting webhook...")
    await bot.delete_webhook()
    logger.info("Bot stopped.")


def main():
    # Регистрация функций жизненного цикла
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Создаем приложение aiohttp
    app = web.Application()

    # Создаем обработчик вебхуков для aiogram
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
        db=db  # Передаем db, чтобы он был доступен в хэндлерах
    )

    # Регистрируем обработчик по нашему секретному пути
    webhook_handler.register(app, path=config.webhook_path)

    # Добавляем "проверку здоровья" на главную страницу
    async def health_check(request):
        return web.Response(text="Bot is running!")

    app.router.add_get("/", health_check)

    # Запускаем веб-сервер aiohttp
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=10000)


if __name__ == "__main__":
    main()