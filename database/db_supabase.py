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
        appointments = []
        for row in rows:
            service_data = row.pop('services', None)
            row['appointment_time'] = parse_datetime(row.get('appointment_time'))
            if not row['appointment_time']:
                logger.warning(f"Skipping appointment due to invalid time: {row.get('id')}")
                continue
            row['created_at'] = parse_datetime(row.get('created_at'))

            # !!! ВАЖНО: Убедитесь, что google_event_id извлекается из row !!!
            # Если он был добавлен в SELECT запрос, то он будет в row.
            # Если поле google_event_id есть в модели Appointment, то оно будет там.
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

    async def get_appointments_for_day(self, target_date: datetime, status: str = 'active') -> List[Appointment]:
        """Получает все записи на указанный день."""
        start_of_day = datetime.combine(target_date.date(), time.min).isoformat()
        end_of_day = datetime.combine(target_date.date(), time.max).isoformat()

        try:
            # !!! ВАЖНО: Убедитесь, что google_event_id выбирается, если он нужен !!!
            # Если его нет в SELECT, то app.google_event_id будет None.
            # Для админ-панели он может быть полезен.
            query = await self.client.table('appointments').select('*, services(title), google_event_id'). \
                gte('appointment_time', start_of_day). \
                lte('appointment_time', end_of_day). \
                order('appointment_time')

            if status:
                query = query.eq('status', status)

            response = await query.execute()  # <-- await execute()
            if not response.data: return []

            return await self._process_appointment_rows(response.data)
        except Exception as e:
            logger.error(f"Error getting appointments for day: {e}")
            return []

    async def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        try:
            # !!! ВАЖНО: Добавляем google_event_id в SELECT !!!
            response = await self.client.table('appointments').select('*, services(title), google_event_id').eq('id',
                                                                                                                appointment_id).limit(
                1).execute()  # <-- await execute()
            if not response.data: return None

            processed_app = await self._process_appointment_rows(response.data)
            return processed_app[0] if processed_app else None
        except Exception as e:
            logger.error(f"Error getting appointment by id: {e}")
            return None

    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
            # !!! ВАЖНО: Добавляем google_event_id в SELECT !!!
            query = await self.client.table('appointments').select('*, services(title), google_event_id'). \
                gte('appointment_time', tomorrow_start). \
                lte('appointment_time', tomorrow_end). \
                eq('status', 'active'). \
                eq('reminded', False).execute()  # <-- await execute()

            if not query.data: return []
            return await self._process_appointment_rows(query.data)
        except Exception as e:
            logger.error(f"Error getting upcoming appointments: {e}")
            return []

    async def mark_as_reminded(self, appointment_id: str):
        try:
            await self.client.table('appointments').update({'reminded': True}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error marking appointment as reminded: {e}")

    async def update_appointment_status(self, appointment_id: str, status: str):
        """Обновляет статус записи и синхронизирует с Google Calendar."""
        appointment = await self.get_appointment_by_id(appointment_id)  # Получаем запись, чтобы узнать google_event_id

        if not appointment:
            logger.warning(f"Не удалось найти запись с ID {appointment_id} для обновления статуса.")
            return

        # --- СИНХРОНИЗАЦИЯ С GOOGLE CALENDAR ---
        # Если есть google_event_id, пытаемся обновить/удалить его
        if appointment.google_event_id:
            if status == 'completed':
                # Для "completed" можно просто обновить событие, например, изменить цвет или добавить заметку.
                # Или, если вам не нужно менять в календаре, то ничего не делаем.
                # Пока что просто логируем.
                logger.info(
                    f"Запись '{appointment_id}' завершена. Google event '{appointment.google_event_id}' не обновляется.")
            elif status == 'cancelled':
                # Если запись отменена, удаляем событие из Google Calendar
                if not utils.google_calendar.delete_google_calendar_event(appointment.google_event_id):
                    logger.warning(
                        f"Не удалось удалить событие Google Calendar '{appointment.google_event_id}' для записи '{appointment_id}'.")
            # Если статус 'active' или другой, который не требует действий в календаре, пропускаем.
            # Если статус 'cancelled' будет использоваться для удаления из БД, то это тоже надо учесть.

        # --- ОБНОВЛЕНИЕ СТАТУСА В БД ---
        try:
            # Обновляем статус записи в нашей базе данных
            await self.client.table('appointments').update({'status': status}).eq('id', appointment_id).execute()
            logger.info(f"Статус записи '{appointment_id}' обновлен на '{status}'.")
        except Exception as e:
            logger.error(f"Error updating status for appointment id {appointment_id}: {e}")

    async def delete_appointment(self, appointment_id: str) -> bool:
        """Удаляет запись из БД и из Google Calendar."""
        # Сначала получаем google_event_id, чтобы удалить соответствующее событие
        appointment = await self.get_appointment_by_id(appointment_id)

        if not appointment:
            logger.warning(f"Не удалось найти запись с ID {appointment_id} для удаления.")
            return False

        # --- СИНХРОНИЗАЦИЯ С GOOGLE CALENDAR ---
        if appointment.google_event_id:
            if not utils.google_calendar.delete_google_calendar_event(appointment.google_event_id):
                logger.warning(
                    f"Не удалось удалить событие Google Calendar '{appointment.google_event_id}' для записи '{appointment_id}'.")

        # --- УДАЛЕНИЕ ИЗ БД ---
        try:
            response = await self.client.table('appointments').delete().eq('id', appointment_id).execute()
            if response and response.data and len(response.data) > 0:
                logger.info(f"Запись '{appointment_id}' успешно удалена.")
                return True
            else:
                logger.warning(f"Удаление записи '{appointment_id}' не дало результата (запись не найдена?).")
                return False
        except Exception as e:
            logger.error(f"Error deleting appointment id {appointment_id}: {e}")
            return False