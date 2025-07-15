# main.py

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
# from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
# from aiohttp import web
from keep_alive import keep_alive

# Удаляем импорт AsyncClient, он не нужен в main
# from supabase import create_client, AsyncClient
from supabase import create_client  # <-- Возвращаем простой импорт create_client

from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# Глобальный обработчик ошибок
error_router = Router()


@error_router.errors()
async def error_handler(exception_update: types.ErrorEvent):
    # ... код обработчика ошибок без изменений ...
    pass  # Оставляем как есть, он не связан с DB инициализацией


# Переменные для вебхука
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default-super-secret")
WEBHOOK_URL = f"{config.web_server_url}{config.webhook_path}"


# --- Функции жизненного цикла приложения ---
# Теперь эти функции не принимают async_supabase_client
async def on_startup(dispatcher: Dispatcher, bot: Bot):
    logger.info("Starting bot and setting webhook...")
    await bot.set_webhook(url=WEBHOOK_URL, secret_token=WEBHOOK_SECRET, drop_pending_updates=True)
    logger.info(f"Webhook is set to {WEBHOOK_URL}")

    # Регистрируем обработчик ошибок ПЕРВЫМ
    dispatcher.include_router(error_router)

    # Регистрируем остальные роутеры
    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)

    # --- ОТКЛЮЧЕНО ДЛЯ ДИАГНОСТИКИ (снова) ---
    # scheduler = setup_scheduler(bot, db) # db будет доступен через data
    # scheduler.start()
    # dispatcher["scheduler"] = scheduler
    logger.info("Scheduler is DISABLED for debugging.")

    logger.info("Bot startup complete.")


# Функция on_shutdown без изменений, scheduler отключен
async def on_shutdown(dispatcher: Dispatcher, bot: Bot):
    logger.info("Shutting down bot and deleting webhook...")
    await bot.delete_webhook()
    logger.info("Webhook deleted.")
    # ... scheduler shutdown code commented out ...
    logger.info("Bot shutdown complete.")


# --- 6. Основная функция запуска ---
def main():
    # --- ИНИЦИАЛИЗИРУЕМ DATABASE ЗДЕСЬ ---
    db = Database(url=config.supabase_url, key=config.supabase_key)
    # -----------------------------------

    # Инициализация хранилища и диспетчера
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    default_properties = DefaultBotProperties(parse_mode="HTML")
    bot = Bot(token=config.bot_token, default=default_properties)

    # Регистрация функций жизненного цикла
    # on_startup и on_shutdown теперь не принимают async_supabase_client
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Создаем веб-приложение aiohttp
    app = web.Application()

    # Создаем обработчик вебхуков для aiogram
    # Передаем объект Database в data для хэндлеров
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
        data={"db": db},  # <--- Передаем экземпляр Database
    )

    # Регистрируем обработчик по нашему секретному пути
    webhook_handler.register(app, path=config.webhook_path)

    # Добавляем "проверку здоровья" на главную страницу
    async def health_check(request):
        return web.Response(text="Bot is running!")

    app.router.add_get("/", health_check)

    # Запускаем веб-сервер aiohttp "из коробки"
    setup_application(app, dp, bot=bot)

    # Определяем порт для Render
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    keep_alive()
    main()