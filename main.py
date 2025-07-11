import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers

# from utils.scheduler import setup_scheduler # --- ОТКЛЮЧЕНО ДЛЯ ДИАГНОСТИКИ ---

# --- 1. Настройка логирования ---
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# --- 2. Инициализация основных объектов ---
db = Database(url=config.supabase_url, key=config.supabase_key)
storage = MemoryStorage()
default_properties = DefaultBotProperties(parse_mode="HTML")

bot = Bot(token=config.bot_token, default=default_properties)
dp = Dispatcher(storage=storage)

# --- 3. Глобальный обработчик ошибок ---
error_router = Router()


@error_router.errors()
async def error_handler(exception_update: types.ErrorEvent):
    update = exception_update.update
    exception = exception_update.exception
    logger.error(f"Произошла критическая ошибка при обработке апдейта {update.update_id}")
    logger.exception(exception)
    try:
        await bot.send_message(
            config.admin_id,
            f"<b>❗️ Произошла ошибка в боте!</b>\n\n"
            f"<b>Тип ошибки:</b> {type(exception).__name__}\n"
            f"<b>Текст ошибки:</b> {exception}\n"
            f"<b>Апдейт:</b> <code>{update.model_dump_json(indent=2, exclude_none=True)}</code>"
        )
    except (TelegramAPIError, Exception) as e:
        logger.error(f"Не удалось отправить сообщение об ошибке админу: {e}")
    return True


# --- 4. Переменные для вебхука ---
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default-super-secret")
WEBHOOK_URL = f"{config.web_server_url}{config.webhook_path}"


# --- 5. Функции жизненного цикла приложения ---
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

    # --- ОТКЛЮЧЕНО ДЛЯ ДИАГНОСТИКИ ---
    # scheduler = setup_scheduler(bot, db)
    # scheduler.start()
    logger.info("Scheduler is DISABLED for debugging.")

    logger.info("Bot startup complete.")


async def on_shutdown(dispatcher: Dispatcher, bot: Bot):
    logger.info("Shutting down bot and deleting webhook...")
    await bot.delete_webhook()
    logger.info("Webhook deleted.")

    # --- ОТКЛЮЧЕНО ДЛЯ ДИАГНОСТИКИ ---
    # scheduler = dispatcher.get("scheduler")
    # if scheduler:
    #     scheduler.shutdown()

    logger.info("Bot shutdown complete.")


# --- 6. Основная функция запуска ---
def main():
    # Регистрация функций жизненного цикла
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Создаем веб-приложение aiohttp
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

    # Запускаем веб-сервер aiohttp "из коробки"
    setup_application(app, dp, bot=bot)

    # Определяем порт для Render
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()