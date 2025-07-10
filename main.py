import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask, request, abort
from asgiref.wsgi import WsgiToAsgi  # <-- НОВЫЙ ИМПОРТ

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

# --- Создание Flask-приложения ---
# Это все еще обычное WSGI-приложение
flask_app = Flask(__name__)

# --- Оборачиваем WSGI-приложение в ASGI-совместимую обертку ---
# Теперь uvicorn будет работать с этим объектом
app = WsgiToAsgi(flask_app)

# --- Вебхук ---
# Важно: мы все еще используем @flask_app.route, а не @app.route
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default-super-secret")
WEBHOOK_URL = f"{config.web_server_url}{config.webhook_path}"


@flask_app.route(config.webhook_path, methods=["POST"])
async def webhook():
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        logger.warning("Incorrect secret token received!")
        abort(403)

    update_data = await request.get_json()
    update = types.Update.model_validate(update_data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update, db=db)

    return "OK"


# --- Функции жизненного цикла ---
async def on_startup(dispatcher: Dispatcher):
    logger.info("Starting bot and setting webhook...")
    await bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET)

    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)

    scheduler = setup_scheduler(bot, db)
    scheduler.start()

    logger.info("Bot started and webhook is set.")


async def on_shutdown(dispatcher: Dispatcher):
    logger.info("Shutting down bot and deleting webhook...")
    await bot.delete_webhook()
    logger.info("Bot stopped.")


def main():
    logger.info("To run locally, use 'uvicorn main:app --reload'")


# --- Регистрация функций жизненного цикла ---
dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)

if __name__ == "__main__":
    main()