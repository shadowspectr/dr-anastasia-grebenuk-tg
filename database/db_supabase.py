import logging
from typing import List, Optional
from dataclasses import asdict
from datetime import datetime, time, timedelta

# Используем только официальную библиотеку supabase
from supabase import create_client, Client as SupabaseConnection
# Убедитесь, что импорт правильный относительно структуры вашего проекта.
# Если db_supabase.py находится в папке utils, а models.py в папке database,
# то импорт может быть таким: from ..database.models import Appointment, Service, ServiceCategory
# Но если они оба находятся в одной папке (например, database), то .models - верно.
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
        # Это может быть рискованно, если нужны точные часовые пояса,
        # но для данного случая, вероятно, достаточно.
        if '+' in iso_string:
            iso_string = iso_string.split('+')[0]
        # Парсим строку
        return datetime.fromisoformat(iso_string)
    except (ValueError, TypeError):
        logger.warning(f"Could not parse datetime string: {iso_string}")
        return None


class Database:
    def __init__(self, url: str, key: str):
        # Важно: Используй async client для асинхронных операций
        self.client: SupabaseConnection = create_client(url, key)

    async def _process_appointment_rows(self, rows: List[dict]) -> List[Appointment]:
        """Вспомогательный метод для обработки списка записей."""
        appointments = []
        for row in rows:
            # Извлекаем данные о сервисе, которые должны быть вложены в ответ от Supabase
            # Предполагается, что при запросе используется select('*, services(title)')
            service_data = row.pop('services', None)

            # Преобразуем строку времени в объект datetime
            row['appointment_time'] = parse_datetime(row.get('appointment_time'))
            if not row['appointment_time']:
                logger.warning(f"Skipping appointment due to invalid time: {row.get('id')}")
                continue  # Пропускаем запись, если дата некорректна

            row['created_at'] = parse_datetime(row.get('created_at'))

            # Создаем объект Appointment
            app = Appointment(**row)
            # Устанавливаем service_title из вложенных данных, если они доступны
            app.service_title = service_data[
                'title'] if service_data and 'title' in service_data else "Удаленная услуга"
            appointments.append(app)
        return appointments

    # --- Методы для Сервисов (Services) ---
    async def get_service_categories(self) -> List[ServiceCategory]:
        """Получает список категорий услуг."""
        try:
            response = self.client.table('service_categories').select('*').order('title').execute()
            if not response.data: return []
            return [ServiceCategory(**row) for row in response.data]
        except Exception as e:
            logger.error(f"Error getting service categories: {e}")
            return []

    async def get_services_by_category(self, category_id: str) -> List[Service]:
        """Получает список услуг по ID категории."""
        try:
            # Важно: Если в модели Service есть duration_minutes, но мы ее больше не используем,
            # можно убрать duration_minutes из SELECT, если он не нужен в объекте Service.
            # Однако, для совместимости с моделью, оставим его, если он там есть.
            # Предполагаем, что в таблице 'services' есть все поля, кроме duration_minutes.
            response = self.client.table('services').select('id, title, description, price, icon, category_id').eq(
                'category_id', category_id).order('title').execute()
            if not response.data: return []
            return [Service(**row) for row in response.data]
        except Exception as e:
            logger.error(f"Error getting services by category: {e}")
            return []

    async def get_service_by_id(self, service_id: str) -> Optional[Service]:
        """Получает услугу по её ID."""
        try:
            # Аналогично, убираем duration_minutes, если он не нужен в объекте Service
            response = self.client.table('services').select('id, title, description, price, icon, category_id').eq('id',
                                                                                                                   service_id).limit(
                1).execute()
            if not response.data: return None
            return Service(**response.data[0])
        except Exception as e:
            logger.error(f"Error getting service by id: {e}")
            return None

    # --- Методы для Записей (Appointments) ---

    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        """Получает записи на завтра, которые еще не были отмечены как напомненные."""
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
            # Используем select('*, services(title)') для получения названия услуги,
            # которое нужно для уведомлений.
            query = self.client.table('appointments').select('*, services(title)') \
                .gte('appointment_time', tomorrow_start) \
                .lte('appointment_time', tomorrow_end) \
                .eq('status', 'active') \
                .eq('reminded', False)

            response = query.execute()
            if not response.data: return []

            return await self._process_appointment_rows(response.data)
        except Exception as e:
            logger.error(f"Error getting upcoming appointments to remind: {e}")
            return []

    async def mark_as_reminded(self, appointment_id: str):
        """Отмечает запись как напомненную."""
        try:
            # Важно: Используй self.client, а не self.async_client, если create_client возвращает async client
            await self.client.table('appointments').update({'reminded': True}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error marking appointment as reminded: {e}")

    async def add_appointment(self, appointment: Appointment) -> Optional[str]:
        """Добавляет новую запись в базу данных."""
        appointment_dict = asdict(appointment)
        # Удаляем поля, которые не должны быть вставлены напрямую или имеют дефолтные значения
        appointment_dict.pop('id', None)
        appointment_dict.pop('created_at', None)
        appointment_dict.pop('service_title', None)
        # appointment_dict.pop('google_event_id', None) # Если поле google_event_id добавлено в модель, но не в БД

        # Убедись, что appointment_time в нужном формате ISO
        appointment_dict['appointment_time'] = appointment.appointment_time.isoformat()

        # Если ты планируешь сохранять google_event_id в базе данных,
        # и это поле есть в твоей таблице appointments в Supabase,
        # то раскомментируй следующие строки:
        # if appointment.google_event_id:
        #     appointment_dict['google_event_id'] = appointment.google_event_id

        try:
            response = self.client.table('appointments').insert(appointment_dict).execute()
            if response and response.data and len(response.data) > 0:
                # Supabase обычно возвращает ID в поле 'id'
                return response.data[0].get('id')
            else:
                logger.error(f"Error adding appointment: Empty response from Supabase.")
                return None
        except Exception as e:
            logger.error(f"Error adding appointment: {e}")
            return None

    async def get_appointments_for_day(self, target_date: datetime, status: str = 'active') -> List[Appointment]:
        """Получает все записи на указанный день."""
        start_of_day = datetime.combine(target_date.date(), time.min).isoformat()
        end_of_day = datetime.combine(target_date.date(), time.max).isoformat()

        try:
            # Используем select('*, services(title)') для получения названия услуги,
            # которое может быть полезно для обработки.
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
        """Получает запись по её ID."""
        try:
            # Используем select('*, services(title)') для получения названия услуги
            response = self.client.table('appointments').select('*, services(title)').eq('id', appointment_id).limit(
                1).execute()
            if not response.data: return None

            # Используем вспомогательный метод (он вернет список из одного элемента)
            processed_app = await self._process_appointment_rows(response.data)
            return processed_app[0] if processed_app else None
        except Exception as e:
            logger.error(f"Error getting appointment by id: {e}")
            return None

    # Метод для планировщика, аналогичен get_upcoming_appointments_to_remind
    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        """Получает записи на завтра, которые еще не были отмечены как напомненные."""
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
            # Используем select('*, services(title)') для получения названия услуги
            query = self.client.table('appointments').select('*, services(title)').gte('appointment_time',
                                                                                       tomorrow_start).lte(
                'appointment_time', tomorrow_end).eq('status', 'active').eq('reminded', False)
            response = query.execute()
            if not response.data: return []
            return await self._process_appointment_rows(response.data)
        except Exception as e:
            logger.error(f"Error getting upcoming appointments: {e}")
            return []

    async def update_appointment_status(self, appointment_id: str, status: str):
        """Обновляет статус записи."""
        try:
            await self.client.table('appointments').update({'status': status}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error updating status for id {appointment_id}: {e}")

    async def delete_appointment(self, appointment_id: str) -> bool:
        """Удаляет запись по её ID."""
        try:
            response = await self.client.table('appointments').delete().eq('id', appointment_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error deleting appointment id {appointment_id}: {e}")
            return False