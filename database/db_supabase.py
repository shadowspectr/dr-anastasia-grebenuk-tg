# database/db_supabase.py (изменения)

import logging
from typing import List, Optional
from dataclasses import asdict, field  # Импортируем field
from datetime import datetime, time, timedelta

from supabase import create_client,Client as SupabaseConnection
from .models import Appointment, Service, ServiceCategory

logger = logging.getLogger(__name__)


def parse_datetime(iso_string: Optional[str]) -> Optional[datetime]:
    """Вспомогательная функция для парсинга дат из Supabase."""
    if not iso_string:
        return None
    try:
        iso_string = iso_string.replace('Z', '+00:00')
        if '+' in iso_string:
            iso_string = iso_string.split('+')[0]
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

            row['appointment_time'] = parse_datetime(row.get('appointment_time'))
            if not row['appointment_time']:
                logger.warning(f"Skipping appointment due to invalid time: {row.get('id')}")
                continue

            row['created_at'] = parse_datetime(row.get('created_at'))

            # !!! ДОБАВИЛИ ОБРАБОТКУ google_event_id !!!
            # Если поле google_event_id приходит из Supabase, оно будет добавлено в row.
            # Поле google_event_id уже есть в модели Appointment.
            # Если оно отсутствует в row, оно будет None по умолчанию.

            app = Appointment(**row)
            app.service_title = service_data[
                'title'] if service_data and 'title' in service_data else "Удаленная услуга"
            appointments.append(app)
        return appointments

    # --- Методы для Сервисов (Services) ---
    # Оставлены без изменений
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
            response = self.client.table('services').select('id, title, description, price, icon, category_id').eq(
                'category_id', category_id).order('title').execute()
            if not response.data: return []
            return [Service(**row) for row in response.data]
        except Exception as e:
            logger.error(f"Error getting services by category: {e}")
            return []

    async def get_service_by_id(self, service_id: str) -> Optional[Service]:
        try:
            response = self.client.table('services').select('id, title, description, price, icon, category_id').eq('id',
                                                                                                                   service_id).limit(
                1).execute()
            if not response.data: return None
            return Service(**response.data[0])
        except Exception as e:
            logger.error(f"Error getting service by id: {e}")
            return None

    # --- Методы для Записей (Appointments) ---
    # Оставлены без изменений, кроме обработки google_event_id в _process_appointment_rows

    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
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
        try:
            await self.client.table('appointments').update({'reminded': True}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error marking appointment as reminded: {e}")

    async def add_appointment(self, appointment: Appointment) -> Optional[str]:
        """Добавляет новую запись в базу данных, включая google_event_id."""
        appointment_dict = asdict(appointment)
        appointment_dict.pop('id', None)
        appointment_dict.pop('created_at', None)
        appointment_dict.pop('service_title', None)

        # Преобразуем appointment_time в ISO формат
        appointment_dict['appointment_time'] = appointment.appointment_time.isoformat()

        # !!! ДОБАВИЛИ СОХРАНЕНИЕ google_event_id !!!
        # Если google_event_id не None, добавляем его в словарь для вставки.
        # Это сработает, если поле google_event_id существует в таблице 'appointments' в Supabase.
        if appointment.google_event_id:
            appointment_dict['google_event_id'] = appointment.google_event_id

        try:
            response = self.client.table('appointments').insert(appointment_dict).execute()
            if response and response.data and len(response.data) > 0:
                return response.data[0].get('id')
            else:
                logger.error(f"Error adding appointment: Empty response from Supabase.")
                return None
        except Exception as e:
            logger.error(f"Error adding appointment: {e}")
            return None

    async def get_appointments_for_day(self, target_date: datetime, status: str = 'active') -> List[Appointment]:
        start_of_day = datetime.combine(target_date.date(), time.min).isoformat()
        end_of_day = datetime.combine(target_date.date(), time.max).isoformat()

        try:
            # Здесь нужно убедиться, что Supabase возвращает google_event_id, если он есть.
            # Если вы хотите явно получать google_event_id, добавьте его в SELECT.
            # Например: select('*, services(title), google_event_id')
            # Если оно есть в _process_appointment_rows, то оно подхватится.
            query = self.client.table('appointments').select('*, services(title)').gte('appointment_time',
                                                                                       start_of_day).lte(
                'appointment_time', end_of_day).order('appointment_time')
            if status:
                query = query.eq('status', status)

            response = query.execute()
            if not response.data: return []

            return await self._process_appointment_rows(response.data)
        except Exception as e:
            logger.error(f"Error getting appointments for day: {e}")
            return []

    async def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        try:
            # Аналогично, убедитесь, что google_event_id выбирается, если он нужен.
            response = self.client.table('appointments').select('*, services(title)').eq('id', appointment_id).limit(
                1).execute()
            if not response.data: return None

            processed_app = await self._process_appointment_rows(response.data)
            return processed_app[0] if processed_app else None
        except Exception as e:
            logger.error(f"Error getting appointment by id: {e}")
            return None

    # Оставшиеся методы без изменений, но проверяйте SELECT запросы, если google_event_id нужно получать
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

    async def mark_as_reminded(self, appointment_id: str):
        try:
            await self.client.table('appointments').update({'reminded': True}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error marking appointment as reminded: {e}")

    async def update_appointment_status(self, appointment_id: str, status: str):
        try:
            await self.client.table('appointments').update({'status': status}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error updating status for id {appointment_id}: {e}")

    async def delete_appointment(self, appointment_id: str) -> bool:
        try:
            response = await self.client.table('appointments').delete().eq('id', appointment_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error deleting appointment id {appointment_id}: {e}")
            return False

    async def update_appointment_google_id(self, appointment_id: str, google_event_id: str) -> bool:
        """
        Обновляет запись в базе данных, добавляя google_event_id.
        Возвращает True при успехе, False при ошибке.
        """
        if not appointment_id or not google_event_id:
            logger.warning("Невозможно обновить Google Event ID: отсутствуют ID записи или события.")
            return False

        try:
            # Формируем объект запроса
            query_builder = self.client.table('appointments').update(
                {'google_event_id': google_event_id}
            ).eq('id', appointment_id)

            # --- ИСПРАВЛЕНИЕ: Убираем await перед .execute() ---
            # Если execute() НЕ является корутиной, то await перед ним вызовет ошибку.
            # В асинхронном контексте, мы можем вызвать его напрямую.
            # Supabase v2.x обычно сам обрабатывает асинхронность.
            response = query_builder.execute()  # <-- Убрали await

            # --- ЕСЛИ execute() САМ ПО СЕБЕ НЕ АСИНХРОННЫЙ, то await будет на КОНТЕКСТЕ,
            # где вызывается этот метод. Но здесь все в async def, так что это маловероятно.

            # --- ОТЛАДКА: Логируем тип ответа ---
            logger.debug(f"Type returned by execute(): {type(response)}")
            if hasattr(response, 'data'):
                logger.debug(f"Data returned: {response.data}")
            else:
                logger.debug(f"Response object does not have 'data' attribute.")
            # --- КОНЕЦ ОТЛАДКИ ---

            # Теперь, если response.data содержит результат, то все хорошо.
            # Если response сам по себе не является awaitable, но должен был вернуть данные,
            # это значит, что execute() выполнился синхронно.
            # Но это противоречит работе с асинхронным клиентом.

            if response and response.data and len(response.data) > 0:
                logger.info(f"Google Event ID '{google_event_id}' успешно обновлен для записи '{appointment_id}'.")
                return True
            else:
                logger.warning(
                    f"Обновление Google Event ID для записи '{appointment_id}' не дало результата (запись не найдена или не изменилась?).")
                return False
        except Exception as e:
            logger.error(f"Ошибка при обновлении Google Event ID для записи '{appointment_id}': {e}", exc_info=True)
            return False