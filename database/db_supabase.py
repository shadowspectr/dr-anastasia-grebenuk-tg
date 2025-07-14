import logging
from typing import List, Optional
from dataclasses import asdict
from datetime import datetime, time, timedelta

from supabase import create_client, AsyncClient
from postgrest import APIResponse

# Исправленный импорт: добавляем Appointment
from .models import ServiceCategory, Service, Appointment # <-- Добавили Appointment

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, key: str):
        # Создаем асинхронный клиент Supabase
        self._client: AsyncClient = create_client(url, key)
        logger.info("Database client initialized.")

    # --- Методы для Услуг и Категорий (переписаны с нуля) ---

    async def get_service_categories(self) -> List[ServiceCategory]:
        """
        Получает список всех категорий услуг.
        """
        logger.debug("Fetching service categories from DB...")
        try:
            # Выполняем асинхронный запрос и ожидаем его результат
            response = await self._client.from_('service_categories').select('*').order('title').execute()
            logger.debug(f"Response from get_service_categories: {response.data}")

            # Проверяем, есть ли данные, и преобразуем их в модели
            if response.data:
                return [ServiceCategory(**row) for row in response.data]
            return []  # Возвращаем пустой список, если данных нет

        except Exception as e:
            logger.error(f"Error fetching service categories: {e}")
            return []

    async def get_services_by_category(self, category_id: str) -> List[Service]:
        """
        Получает список услуг по ID категории.
        """
        logger.debug(f"Fetching services for category_id: {category_id} from DB...")
        try:
            # Выполняем асинхронный запрос с фильтром по category_id
            response = await self._client.from_('services').select('*').eq('category_id', category_id).order(
                'title').execute()
            logger.debug(f"Response from get_services_by_category: {response.data}")

            if response.data:
                return [Service(**row) for row in response.data]
            return []

        except Exception as e:
            logger.error(f"Error fetching services for category_id {category_id}: {e}")
            return []

    async def get_service_by_id(self, service_id: str) -> Optional[Service]:
        """
        Получает одну услугу по ее ID.
        """
        logger.debug(f"Fetching service by id: {service_id} from DB...")
        try:
            # Выполняем запрос и ожидаем одну запись
            response = await self._client.from_('services').select('*').eq('id', service_id).limit(1).single().execute()
            logger.debug(f"Response from get_service_by_id: {response.data}")

            if response.data:
                # single().execute() возвращает один объект в response.data
                return Service(**response.data)
            return None  # Возвращаем None, если услуга не найдена

        except Exception as e:
            logger.error(f"Error fetching service by id {service_id}: {e}")
            return None

    # --- ЗАГЛУШКИ для других методов ---
    # Эти методы пока не нужны для логики выбора услуги,
    # но должны быть определены, если их вызывают хэндлеры.
    # Вернемся к ним позже, если они понадобятся для других частей бота.

    async def add_appointment(self, appointment) -> Optional[str]:
        logger.warning("add_appointment not implemented yet.")
        return None  # Пока просто заглушка

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