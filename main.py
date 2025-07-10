import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask, request, abort

from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler

# Инициализация
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

db = Database(url=config.supabase_url, key=config.supabase_key)
storage = MemoryStorage()
default_properties = DefaultBotProperties(parse_mode="HTML")

bot = Bot(token=config.bot_token, default=default_properties)
dp = Dispatcher(storage=storage)

# Создаем Flask-приложение
app = Flask(__name__)

# Секретный токен для проверки, что запросы приходят от Telegram
# Его можно добавить в переменные окружения для большей безопасности
WEBHOOK_SECRET = "some-super-secret-string"  # Или взять из config


@app.route(config.webhook_path, methods=["POST"])
async def webhook():
    """
    Этот хэндлер будет принимать вебхуки от Telegram
    """
    # Проверяем секретный заголовок
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        abort(403)

    # Получаем обновление и передаем его в Dispatcher
    update_data = await request.get_json()
    update = types.Update.model_validate(update_data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update, db=db)

    # Возвращаем OK, чтобы Telegram знал, что мы получили обновление
    return "OK"


async def on_startup():
    """
    Выполняется один раз при старте. Устанавливает вебхук.
    """
    logger.info("Starting bot and setting webhook...")

    # Устанавливаем вебхук
    webhook_url = f"{config.web_server_url}{config.webhook_path}"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=WEBHOOK_SECRET
    )

    # Регистрируем роутеры
    dp.include_router(common_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(client_handlers.router)

    # Запускаем планировщик
    scheduler = setup_scheduler(bot, db)
    scheduler.start()

    logger.info("Bot started and webhook is set.")


async def on_shutdown():
    """
    Выполняется при остановке. Удаляет вебхук.
    """
    logger.info("Shutting down bot and deleting webhook...")
    await bot.delete_webhook()
    logger.info("Bot stopped.")


def main():
    """
    Функция для локального запуска (не используется на Render)
    """
    # Регистрируем функции старта и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Запускаем Flask приложение
    # Для локальной отладки можно использовать: app.run(debug=True)
    # Но gunicorn - это для продакшена
    logger.info("This is a local runner. For production, use Gunicorn.")


if __name__ == "__main__":
    # Эта часть не будет выполняться на Render,
    # так как Gunicorn запускает приложение по-другому
    asyncio.run(on_startup())
    # Для тестов можно запустить Flask-сервер так:
    # app.run(host='0.0.0.0', port=8000)