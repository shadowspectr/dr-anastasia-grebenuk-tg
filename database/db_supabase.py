# database/db_supabase.py

import logging
from typing import List, Optional
from dataclasses import asdict
from datetime import datetime, time

# Используем асинхронный клиент из официальной библиотеки
from supabase import create_client, AClient as AsyncSupabaseConnection
from .models import Appointment, Service, ServiceCategory

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, key: str):
        # Создаем экземпляр асинхронного клиента
        self.async_client: AsyncSupabaseConnection = create_client(url, key)

    # --- Вспомогательные методы (остаются без изменений) ---
    async def _process_appointment_rows(self, rows: List[dict]) -> List[Appointment]:
        # ... (этот метод был в вашем примере, но он не нужен, если правильно парсить)
        # Упростим и будем парсить на лету
        pass

    # --- Методы для Услуг и Категорий ---
    async def get_service_categories(self) -> List[ServiceCategory]:
        try:
            response = await self.async_client.table('service_categories').select('*').order('title').get()
            return [ServiceCategory(**row) for row in response.data] if response.data else []
        except Exception as e:
            logger.error(f"Error getting service categories: {e}")
            return []

    async def get_services_by_category(self, category_id: str) -> List[Service]:
        try:
            response = await self.async_client.table('services').select('*').eq('category_id', category_id).order(
                'title').get()
            return [Service(**row) for row in response.data] if response.data else []
        except Exception as e:
            logger.error(f"Error getting services by category: {e}")
            return []

    async def get_service_by_id(self, service_id: str) -> Optional[Service]:
        try:
            response = await self.async_client.table('services').select('*').eq('id', service_id).limit(
                1).single().get()
            return Service(**response.data) if response.data else None
        except Exception as e:
            logger.error(f"Error getting service by id: {e}")
            return None

    # --- Методы для Записей (Appointments) ---

    async def add_appointment(self, appointment: Appointment) -> Optional[str]:
        """Сохраняет запись в БД, включая google_event_id."""
        appointment_dict = asdict(appointment)
        # Убираем поля, которые не должны идти в insert
        for key in ['id', 'created_at', 'service_title']:
            appointment_dict.pop(key, None)
        # Убедимся, что время в правильном формате
        if isinstance(appointment.appointment_time, datetime):
            appointment_dict['appointment_time'] = appointment.appointment_time.isoformat()

        try:
            response = await self.async_client.table('appointments').insert(appointment_dict).get()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error adding appointment: {e}")
            return None

    async def get_appointment_by_google_id(self, google_event_id: str) -> Optional[Appointment]:
        """Находит запись в БД по ID события Google."""
        try:
            response = await self.async_client.table('appointments').select('*, services(title)').eq('google_event_id',
                                                                                                     google_event_id).limit(
                1).single().get()
            if not response.data: return None

            row = response.data
            service_data = row.pop('services', None)
            app = Appointment(**row)
            app.service_title = service_data['title'] if service_data else "Удаленная услуга"
            return app
        except Exception as e:
            logger.error(f"Error getting appointment by google_id: {e}")
            return None

    async def delete_appointment_by_google_id(self, google_event_id: str) -> bool:
        """Удаляет запись из БД по ID события Google."""
        try:
            await self.async_client.table('appointments').delete().eq('google_event_id', google_event_id).execute()
            logger.info(f"Successfully deleted appointment from DB with google_event_id: {google_event_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting appointment by google_id: {e}")
            return False

    # --- Методы для планировщика ---

    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        """Получает записи для напоминаний (на завтра)."""
        from datetime import timedelta  # Локальный импорт

        tomorrow = datetime.now() + timedelta(days=1)
        start_of_day = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
            query = self.async_client.table('appointments').select('*, services(title)') \
                .gte('appointment_time', start_of_day) \
                .lte('appointment_time', end_of_day) \
                .eq('status', 'active') \
                .eq('reminded', False)

            response = await query.get()
            if not response.data: return []

            appointments = []
            for row in response.data:
                service_data = row.pop('services', None)
                app = Appointment(**row)
                app.service_title = service_data['title'] if service_data else "Удаленная услуга"
                appointments.append(app)
            return appointments
        except Exception as e:
            logger.error(f"Error getting upcoming appointments to remind: {e}")
            return []

    async def mark_as_reminded(self, appointment_id: str):
        """Помечает запись как 'напомнено'."""
        try:
            # update и delete требуют .execute() в конце
            await self.async_client.table('appointments').update({'reminded': True}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error marking appointment as reminded: {e}")