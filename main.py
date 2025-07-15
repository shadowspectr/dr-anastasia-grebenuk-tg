# main.py

import asyncio
import logging
import os
import signal # Для корректного завершения работы

from aiogram import Bot, Dispatcher, types, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from config_reader import config
from database.db_supabase import Database
from handlers import common_handlers, admin_handlers, client_handlers
from utils.scheduler import setup_scheduler
# Импортируем функцию для запуска бота в отдельном потоке
from keep_alive import start_polling_in_thread

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# Глобальный обработчик ошибок
error_router = Router()

@error_router.errors()
async def error_handler(exception_update: types.ErrorEvent):
    """Обработчик ошибок для aiogram."""
    exception = exception_update.exception
    update = exception_update.update
    logger.error(f"Update: {update}")
    logger.error(f"Error: {exception}")
    # Можно добавить более детальную обработку ошибок, например, отправку админу
    # await exception_update.bot.send_message(config.admin_id, f"Произошла ошибка: {exception}")

# --- Функции жизненного цикла приложения ---
async def on_startup(dispatcher: Dispatcher, db: Database):
    """Выполняется при старте бота."""
    logger.info("Starting bot and registering handlers...")

    # Регистрируем роутеры
    dispatcher.include_router(error_router) # Обработчик ошибок должен быть первым
    dispatcher.include_router(common_handlers.router)
    dispatcher.include_router(admin_handlers.router)
    dispatcher.include_router(client_handlers.router)

    # Инициализация и запуск планировщика, если база данных доступна
    if db:
        try:
            scheduler = setup_scheduler(dispatcher.bot, db)
            scheduler.start()
            dispatcher["scheduler"] = scheduler
            logger.info("Scheduler started.")
        except Exception as e:
            logger.exception(f"Failed to start scheduler: {e}")
    else:
        logger.warning("Database not initialized, scheduler will not be started.")

    logger.info("Bot startup complete.")

async def on_shutdown(dispatcher: Dispatcher):
    """Выполняется при выключении бота."""
    logger.info("Shutting down bot...")
    # Корректное завершение работы планировщика
    if "scheduler" in dispatcher and dispatcher["scheduler"]:
        try:
            dispatcher["scheduler"].shutdown()
            logger.info("Scheduler shut down.")
        except Exception as e:
            logger.exception(f"Error shutting down scheduler: {e}")
    # Очистка FSM состояний (опционально)
    await dispatcher.storage.close()
    logger.info("Bot shutdown complete.")

# --- Основная функция запуска ---
def main():
    """Инициализирует бота и запускает его в режиме polling."""
    logger.info("Initializing bot components...")

    # ИНИЦИАЛИЗИРУЕМ DATABASE
    try:
        db = Database(url=config.supabase_url, key=config.supabase_key)
        # Проверка соединения с БД (опционально, но рекомендуется)
        # Можно добавить вызов какого-нибудь метода для проверки
        logger.info("Database connection established.")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        db = None # Устанавливаем db в None, если инициализация не удалась

    # Инициализация хранилища состояний и диспетчера
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    # Настройка свойств бота (например, парсинг HTML)
    default_properties = DefaultBotProperties(parse_mode="HTML")
    bot = Bot(token=config.bot_token, default=default_properties)

    # Регистрация обработчиков жизненного цикла
    # Передаем экземпляр db в on_startup
    dp.startup.register(on_startup, db=db)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot in polling mode...")

    # Запускаем бота в режиме polling в отдельном потоке
    # Функция start_polling_in_thread находится в keep_alive.py
    # Она создаст поток, который запустит asyncio.run(dp.start_polling(bot))
    start_polling_in_thread(dp, bot)

    logger.info("Bot polling started in a separate thread.")
    logger.info("Main process is now running to keep the bot alive.")

    # Здесь можно добавить код для поддержания активности основного процесса,
    # если это необходимо платформе (например, простой HTTP-сервер, если keep_alive.py
    # теперь используется только для запуска бота, а не для HTTP-сервера).
    # В данном случае, мы предполагаем, что start_polling_in_thread уже создал
    # управляющий поток, и этот main процесс просто должен работать.
    # Для простоты, мы можем просто ожидать сигналов завершения.

    # Создаем loop для обработки сигналов
    loop = asyncio.get_event_loop()

    # Добавляем обработчик сигналов
    def handle_signal(signum, frame):
        logger.info(f"Signal {signum} received. Shutting down...")
        # Отправляем сигнал завершения диспетчеру
        # Это может потребовать более сложной логики, чтобы остановить потоки правильно
        # Для простоты, можно просто завершить приложение
        loop.stop() # Останавливает цикл событий, если он все еще работает
        # Возможно, потребуется явный вызов dp.stop() или bot.session.close()
        # Но обычно aiogram сам обрабатывает остановку при выходе из asyncio.run

    # Регистрируем сигналы SIGINT (Ctrl+C) и SIGTERM (для системных остановок)
    try:
        loop.add_signal_handler(signal.SIGINT, handle_signal, signal.SIGINT, None)
        loop.add_signal_handler(signal.SIGTERM, handle_signal, signal.SIGTERM, None)
    except NotImplementedError:
        # Для Windows, add_signal_handler может быть недоступен
        logger.warning("Signal handlers for SIGINT/SIGTERM not available on this OS.")

    # Оставляем основной поток работать, пока цикл событий не будет остановлен
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Main process interrupted.")
    finally:
        logger.info("Cleaning up main process...")
        # Здесь можно добавить код очистки, если он нужен для основного процесса
        # Например, закрытие сессии бота, если она не закрывается автоматически
        # if bot:
        #     asyncio.run(bot.session.close())
        logger.info("Main process finished.")


if __name__ == "__main__":
    main()