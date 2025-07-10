import logging
from typing import List, Optional
from dataclasses import asdict
from datetime import datetime, time

# Используем только официальную библиотеку supabase
from supabase import create_client, Client as SupabaseConnection
from .models import Appointment, Service, ServiceCategory

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, key: str):
        # Создаем обычный, синхронный клиент
        self.client: SupabaseConnection = create_client(url, key)

    # --- Методы для Услуг и Категорий ---
    # Функции остаются async def, потому что их вызывает aiogram,
    # но внутри они выполняют блокирующий (синхронный) код.

    async def get_service_categories(self) -> List[ServiceCategory]:
        try:
            # Убираем await, так как вызов синхронный
            response = self.client.table('service_categories').select('*').order('title').execute()
            if not response.data: return []
            return [ServiceCategory(**row) for row in response.data]
        except Exception as e:
            logger.error(f"Error getting service categories: {e}")
            return []

    async def get_services_by_category(self, category_id: str) -> List[Service]:
        try:
            response = self.client.table('services').select('*').eq('category_id', category_id).order('title').execute()
            if not response.data: return []
            return [Service(**row) for row in response.data]
        except Exception as e:
            logger.error(f"Error getting services by category: {e}")
            return []

    async def get_service_by_id(self, service_id: str) -> Optional[Service]:
        try:
            response = self.client.table('services').select('*').eq('id', service_id).limit(1).execute()
            if not response.data: return None
            return Service(**response.data[0])
        except Exception as e:
            logger.error(f"Error getting service by id: {e}")
            return None

    # --- Методы для Записей (Appointments) ---

    async def add_appointment(self, appointment: Appointment) -> Optional[str]:
        appointment_dict = asdict(appointment)
        for key in ['id', 'created_at', 'service_title']:
            appointment_dict.pop(key, None)
        appointment_dict['appointment_time'] = appointment.appointment_time.isoformat()

        try:
            response = self.client.table('appointments').insert(appointment_dict).execute()
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            logger.error(f"Error adding appointment: {e}")
            return None

    async def get_appointments_for_day(self, target_date: datetime, status: str = 'active') -> List[Appointment]:
        start_of_day = datetime.combine(target_date.date(), time.min).isoformat()
        end_of_day = datetime.combine(target_date.date(), time.max).isoformat()

        try:
            query = self.client.table('appointments').select('*, services(title)').gte('appointment_time',
                                                                                       start_of_day).lte(
                'appointment_time', end_of_day).order('appointment_time')
            if status:
                query = query.eq('status', status)

            response = query.execute()
            if not response.data: return []

            appointments = []
            for row in response.data:
                service_data = row.pop('services', None)
                app = Appointment(**row)
                app.service_title = service_data['title'] if service_data else "Удаленная услуга"
                appointments.append(app)
            return appointments
        except Exception as e:
            logger.error(f"Error getting appointments for day: {e}")
            return []

    async def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        try:
            response = self.client.table('appointments').select('*, services(title)').eq('id', appointment_id).limit(
                1).execute()
            if not response.data: return None

            row = response.data[0]
            service_data = row.pop('services', None)
            app = Appointment(**row)
            app.service_title = service_data['title'] if service_data else "Удаленная услуга"
            return app
        except Exception as e:
            logger.error(f"Error getting appointment by id: {e}")
            return None