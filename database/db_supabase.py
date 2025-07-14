# database/db_supabase.py

import logging
from typing import List, Optional
# Пока не импортируем dataclasses, datetime, time, timedelta, т.к. они не нужны для методов категорий/услуг
# from dataclasses import asdict
# from datetime import datetime, time, timedelta

# Используем стандартный импорт create_client и AsyncClient
# APIResponse не нужен для базовых вызовов
from supabase import create_client, AsyncClient

# Импортируем модели, которые используются в возвращаемых типах
from .models import ServiceCategory, Service, Appointment  # Убедитесь, что эти модели правильно определены в models.py

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, key: str):
        """
        Инициализирует клиент базы данных.
        """
        # Создаем асинхронный клиент Supabase
        # create_client в supabase-py v2 сам возвращает AsyncClient
        self._client: AsyncClient = create_client(url, key)
        logger.info("Database client initialized with AsyncClient.")

    # --- Методы для Услуг и Категорий (ПЕРЕПИСАНЫ С НУЛЯ) ---

    async def get_service_categories(self) -> List[ServiceCategory]:
        """
        Получает список всех категорий услуг из таблицы 'service_categories'.
        """
        logger.debug("Attempting to fetch service categories from DB...")
        try:
            # Используем from_() для обращения к таблице
            # Выполняем select и order, затем ожидаем результат execute()
            response = await self._client.from_('service_categories').select('*').order('title').execute()
            logger.debug(f"Raw response data for categories: {response.data}")

            # Проверяем, есть ли данные, и преобразуем их в список моделей ServiceCategory
            if response.data:
                # Используем **row для передачи данных в конструктор модели
                categories = [ServiceCategory(**row) for row in response.data]
                logger.debug(f"Fetched {len(categories)} service categories.")
                return categories

            logger.debug("No service categories found.")
            return []  # Возвращаем пустой список, если данных нет

        except Exception as e:
            # Логируем тип ошибки и текст для отладки
            logger.error(f"Error fetching service categories. Error type: {type(e).__name__}. Error: {e}")
            return []  # В случае ошибки также возвращаем пустой список

    async def get_services_by_category(self, category_id: str) -> List[Service]:
        """
        Получает список услуг из таблицы 'services' по ID категории.
        """
        logger.debug(f"Attempting to fetch services for category_id: {category_id} from DB...")
        try:
            # Выполняем select с фильтром по category_id, затем ожидаем execute()
            response = await self._client.from_('services').select('*').eq('category_id', category_id).order(
                'title').execute()
            logger.debug(f"Raw response data for services (category={category_id}): {response.data}")

            if response.data:
                # Преобразуем данные в список моделей Service
                services = [Service(**row) for row in response.data]
                logger.debug(f"Fetched {len(services)} services for category {category_id}.")
                return services

            logger.debug(f"No services found for category {category_id}.")
            return []

        except Exception as e:
            logger.error(
                f"Error fetching services for category_id {category_id}. Error type: {type(e).__name__}. Error: {e}")
            return []

    async def get_service_by_id(self, service_id: str) -> Optional[Service]:
        """
        Получает одну услугу из таблицы 'services' по ее ID.
        """
        logger.debug(f"Attempting to fetch service by id: {service_id} from DB...")
        try:
            # Выполняем select с фильтром по id, используем limit(1).single() для одной записи, ожидаем execute()
            response = await self._client.from_('services').select('*').eq('id', service_id).limit(1).single().execute()
            logger.debug(f"Raw response data for service (id={service_id}): {response.data}")

            # single().execute() возвращает один объект в response.data, если найден
            if response.data:
                service = Service(**response.data)
                logger.debug(f"Fetched service by id {service_id}: {service.title}")
                return service

            logger.debug(f"Service with id {service_id} not found.")
            return None  # Возвращаем None, если услуга не найдена

        except Exception as e:
            logger.error(f"Error fetching service by id {service_id}. Error type: {type(e).__name__}. Error: {e}")
            return None

    # --- ЗАГЛУШКИ для других методов ---
    # Эти методы пока не реализованы, чтобы сфокусироваться на категориях/услугах.
    # Если их вызывает какой-то хэндлер, он получит Warning и None/False.
    # Добавим их позже по мере необходимости.

    async def add_appointment(self, appointment: Appointment) -> Optional[str]:
        logger.warning("add_appointment not implemented yet.")
        return None

    async def delete_appointment(self, app_id: str) -> bool:
        logger.warning("delete_appointment not implemented yet.")
        return False

    async def update_appointment_status(self, app_id: str, status: str):
        logger.warning("update_appointment_status not implemented yet.")
        pass

    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        logger.warning("get_upcoming_appointments_to_remind not implemented yet.")
        return []

    async def mark_as_reminded(self, appointment_id: str):
        logger.warning("mark_as_reminded not implemented yet.")
        pass

    async def get_appointments_for_day(self, target_date: datetime) -> List[Appointment]:
        logger.warning("get_appointments_for_day not implemented yet.")
        return []

    async def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        logger.warning("get_appointment_by_id not implemented yet.")
        return None