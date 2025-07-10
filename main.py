import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask, request, abort

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
app = Flask(__name__)

# --- Вебхук ---
# Лучше вынести секрет в переменные окружения для безопасности
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default-super-secret")
WEBHOOK_URL = f"{config.web_server_url}{config.webhook_path}"


@app.route(config.webhook_path, methods=["POST"])
async def webhook():
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        logger.warning("Incorrect secret token received!")
        abort(403)

    update_data = await request.get_json()
    update = types.Update.model_validate(update_data, context={"bot": bot})
    # Передаем db в обработчик, чтобы он был доступен в хэндлерах
    await dp.feed_update(bot=bot, update=update, db=db)

    return "OK"


# --- Функции жизненного цикла ---
async def on_startup(dispatcher: Dispatcher):
    logger.info("Starting bot and setting webhook...")
    await bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET)

    # Регистрация роутеров
    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)

    # Запуск планировщика
    scheduler = setup_scheduler(bot, db)
    scheduler.start()

    logger.info("Bot started and webhook is set.")


async def on_shutdown(dispatcher: Dispatcher):
    logger.info("Shutting down bot and deleting webhook...")
    await bot.delete_webhook()
    logger.info("Bot stopped.")


def main():
    # Эта функция больше не нужна для запуска, но может пригодиться для локальных тестов
    logger.info("To run locally, use 'uvicorn main:app --reload'")


# --- Регистрация функций жизненного цикла ---
# Важно! Это должно быть в глобальной области видимости,
# чтобы gunicorn/uvicorn могли это увидеть при импорте.
dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)

if __name__ == "__main__":
    # Эта часть для локального запуска
    # uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    main()