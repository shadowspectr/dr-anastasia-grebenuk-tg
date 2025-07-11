import logging
from typing import List, Optional
from dataclasses import asdict
from datetime import datetime, time, timedelta

# Используем только официальную библиотеку supabase
from supabase import create_client, Client as SupabaseConnection
from .models import Appointment, Service, ServiceCategory

logger = logging.getLogger(__name__)


def parse_datetime(iso_string: Optional[str]) -> Optional[datetime]:
    """Вспомогательная функция для парсинга дат из Supabase."""
    if not iso_string:
        return None
    try:
        # Supabase может возвращать дату с 'Z' или с '+00:00'
        iso_string = iso_string.replace('Z', '+00:00')
        # Отбрасываем информацию о таймзоне, если она есть, для простоты
        if '+' in iso_string:
            iso_string = iso_string.split('+')[0]
        # Парсим строку
        return datetime.fromisoformat(iso_string)
    except (ValueError, TypeError):
        logger.warning(f"Could not parse datetime string: {iso_string}")
        return None


class Database:
    def __init__(self, url: str, key: str):
        self.client: SupabaseConnection = create_client(url, key)

    async def _process_appointment_rows(self, rows: List[dict]) -> List[Appointment]:
        """Вспомогательный метод для обработки списка записей."""
        appointments = []
        for row in rows:
            service_data = row.pop('services', None)

            # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
            # Преобразуем строку времени в объект datetime
            row['appointment_time'] = parse_datetime(row.get('appointment_time'))
            if not row['appointment_time']:
                continue  # Пропускаем запись, если дата некорректна

            row['created_at'] = parse_datetime(row.get('created_at'))
            # ---------------------------

            app = Appointment(**row)
            app.service_title = service_data['title'] if service_data else "Удаленная услуга"
            appointments.append(app)
        return appointments

    # ... (методы для услуг остаются без изменений) ...
    async def get_service_categories(self) -> List[ServiceCategory]:
        try:
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

    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        # Определяем начало и конец завтрашнего дня
        tomorrow_start = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0,
                                                                      microsecond=0).isoformat()
        tomorrow_end = (datetime.now() + timedelta(days=1)).replace(hour=23, minute=59, second=59,
                                                                    microsecond=999999).isoformat()

        try:
            query = self.async_client.table('appointments').select('*, services(title)') \
                .gte('appointment_time', tomorrow_start) \
                .lte('appointment_time', tomorrow_end) \
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
        try:
            await self.async_client.table('appointments').update({'reminded': True}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error marking appointment as reminded: {e}")

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

            # Используем вспомогательный метод для обработки
            return await self._process_appointment_rows(response.data)
        except Exception as e:
            logger.error(f"Error getting appointments for day: {e}")
            return []

    async def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        try:
            response = self.client.table('appointments').select('*, services(title)').eq('id', appointment_id).limit(
                1).execute()
            if not response.data: return None

            # Используем вспомогательный метод (он вернет список из одного элемента)
            processed_app = await self._process_appointment_rows(response.data)
            return processed_app[0] if processed_app else None
        except Exception as e:
            logger.error(f"Error getting appointment by id: {e}")
            return None

    # Переписываем метод для планировщика тоже
    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
            query = self.client.table('appointments').select('*, services(title)').gte('appointment_time',
                                                                                       tomorrow_start).lte(
                'appointment_time', tomorrow_end).eq('status', 'active').eq('reminded', False)
            response = query.execute()
            if not response.data: return []
            return await self._process_appointment_rows(response.data)
        except Exception as e:
            logger.error(f"Error getting upcoming appointments: {e}")
            return []

    # Методы обновления остаются без изменений
    async def mark_as_reminded(self, appointment_id: str):
        try:
            self.client.table('appointments').update({'reminded': True}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error marking as reminded for id {appointment_id}: {e}")

    async def update_appointment_status(self, appointment_id: str, status: str):
        try:
            self.client.table('appointments').update({'status': status}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error updating status for id {appointment_id}: {e}")

    async def delete_appointment(self, appointment_id: str) -> bool:
        try:
            response = self.client.table('appointments').delete().eq('id', appointment_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error deleting appointment id {appointment_id}: {e}")
            return False