# database/db_supabase.py

import logging
from typing import List, Optional
from dataclasses import asdict, field
from datetime import datetime, time, timedelta

# Импортируем asyncio для to_thread
import asyncio

# Используем только официальную библиотеку supabase
# Убедитесь, что create_client возвращает правильный клиент (асинхронный)
from supabase import create_client, Client as SupabaseConnection
from .models import Appointment, Service, ServiceCategory
import utils.google_calendar  # Импортируем для использования функций Google Calendar

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
        # --- Важно: Убедитесь, что create_client настроен для асинхронной работы ---
        # Хотя .execute() может вести себя синхронно, клиент должен быть асинхронным.
        self.client = create_client(url, key)  # Явно указываем async_client=True

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

            # Убеждаемся, что google_event_id извлекается из row, если он там есть
            app = Appointment(**row)
            app.service_title = service_data[
                'title'] if service_data and 'title' in service_data else "Удаленная услуга"
            appointments.append(app)
        return appointments

    # --- Методы для Сервисов (Services) ---
    # Оставлены без изменений, но методы execute() должны быть вызваны через asyncio.to_thread
    async def get_service_categories(self) -> List[ServiceCategory]:
        try:
            # --- ИСПРАВЛЕНИЕ: Вызов синхронного execute через asyncio.to_thread ---
            response = await asyncio.to_thread(self.client.table('service_categories').select('*').order(
                'title').execute)  # <-- execute() без await, но обернут в to_thread
            if not response.data: return []
            return [ServiceCategory(**row) for row in response.data]
        except Exception as e:
            logger.error(f"Error getting service categories: {e}")
            return []

    async def get_service_categories(self) -> List[ServiceCategory]:
        try:
            # --- ВАЖНО: Убедитесь, что execute() вызывается корректно ---
            # Используйте asyncio.to_thread, если execute() синхронный
            response = await asyncio.to_thread(
                self.client.table('service_categories').select('*').order('title').execute)
            if not response.data: return []
            return [ServiceCategory(**row) for row in response.data]
        except Exception as e:
            logger.error(f"Error getting service categories: {e}")
            return []

    # --- ВОЗВРАЩАЕМ МЕТОД get_services_by_category ---
    async def get_services_by_category(self, category_id: str) -> List[Service]:
        """Получает список услуг по ID категории."""
        try:
            # --- ВАЖНО: Убедитесь, что execute() вызывается корректно ---
            # Используйте asyncio.to_thread, если execute() синхронный
            response = await asyncio.to_thread(
                self.client.table('services').select('id, title, description, price, icon, category_id').eq(
                    'category_id', category_id).order('title').execute)
            if not response.data: return []
            return [Service(**row) for row in response.data]
        except Exception as e:
            logger.error(f"Error getting services by category: {e}")
            return []

    async def get_service_by_id(self, service_id: str) -> Optional[Service]:
        try:
            # --- ВАЖНО: Убедитесь, что execute() вызывается корректно ---
            response = await asyncio.to_thread(
                self.client.table('services').select('id, title, description, price, icon, category_id').eq('id',
                                                                                                            service_id).limit(
                    1).execute)
            if not response.data: return None
            return Service(**response.data[0])
        except Exception as e:
            logger.error(f"Error getting service by id: {e}")
            return None

    async def get_appointments_for_day(self, target_date: datetime, status: str = 'active') -> List[Appointment]:
        """Получает все записи на указанный день."""
        start_of_day = datetime.combine(target_date.date(), time.min).isoformat()
        end_of_day = datetime.combine(target_date.date(), time.max).isoformat()

        try:
            query_builder = self.client.table('appointments').select('*, services(title), google_event_id'). \
                gte('appointment_time', start_of_day). \
                lte('appointment_time', end_of_day). \
                order('appointment_time')
            if status:
                query_builder = query_builder.eq('status', status)

            # --- ИСПРАВЛЕНИЕ: Вызов синхронного execute через asyncio.to_thread ---
            response = await asyncio.to_thread(query_builder.execute)
            # ---

            if not response.data: return []
            return await self._process_appointment_rows(response.data)
        except Exception as e:
            logger.error(f"Error getting appointments for day: {e}", exc_info=True)
            return []

    async def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        """Получает запись по её ID."""
        try:
            query_builder = self.client.table('appointments').select('*, services(title), google_event_id').eq('id',
                                                                                                               appointment_id).limit(
                1)

            # --- ИСПРАВЛЕНИЕ: Вызов синхронного execute через asyncio.to_thread ---
            response = await asyncio.to_thread(query_builder.execute)
            # ---

            if not response.data: return None

            processed_app = await self._process_appointment_rows(response.data)
            return processed_app[0] if processed_app else None
        except Exception as e:
            logger.error(f"Error getting appointment by id: {e}", exc_info=True)
            return None

    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
            query_builder = self.client.table('appointments').select('*, services(title), google_event_id'). \
                gte('appointment_time', tomorrow_start). \
                lte('appointment_time', tomorrow_end). \
                eq('status', 'active'). \
                eq('reminded', False)

            # --- ИСПРАВЛЕНИЕ: Вызов синхронного execute через asyncio.to_thread ---
            response = query_builder.execute()  # <-- Без await, но обернем в to_thread
            response = await asyncio.to_thread(response)  # <-- await-им сам результат execute, если он не корутина
            # ---

            if not response.data: return []
            return await self._process_appointment_rows(response.data)
        except Exception as e:
            logger.error(f"Error getting upcoming appointments: {e}")
            return []

    async def mark_as_reminded(self, appointment_id: str):
        try:
            # --- ИСПРАВЛЕНИЕ: Вызов синхронного execute через asyncio.to_thread ---
            query_builder = self.client.table('appointments').update({'reminded': True}).eq('id', appointment_id)
            await asyncio.to_thread(query_builder.execute)  # <-- Без await на execute, но await на to_thread
            # ---
        except Exception as e:
            logger.error(f"Error marking appointment as reminded: {e}")

    async def update_appointment_status(self, appointment_id: str, status: str):
        appointment = await self.get_appointment_by_id(appointment_id)

        if not appointment:
            logger.warning(f"Не удалось найти запись с ID {appointment_id} для обновления статуса.")
            return

        # --- СИНХРОНИЗАЦИЯ С GOOGLE CALENDAR ---
        if appointment.google_event_id:
            if status == 'completed':
                logger.info(
                    f"Запись '{appointment_id}' завершена. Google event '{appointment.google_event_id}' не обновляется.")
            elif status == 'cancelled':
                if not utils.google_calendar.delete_google_calendar_event(appointment.google_event_id):
                    logger.warning(
                        f"Не удалось удалить событие Google Calendar '{appointment.google_event_id}' для записи '{appointment_id}'.")

        # --- ОБНОВЛЕНИЕ СТАТУСА В БД ---
        try:
            # --- ИСПРАВЛЕНИЕ: Вызов синхронного execute через asyncio.to_thread ---
            query_builder = self.client.table('appointments').update({'status': status}).eq('id', appointment_id)
            await asyncio.to_thread(query_builder.execute)  # <-- Без await на execute, но await на to_thread
            # ---
            logger.info(f"Статус записи '{appointment_id}' обновлен на '{status}'.")
        except Exception as e:
            logger.error(f"Error updating status for appointment id {appointment_id}: {e}")

    async def delete_appointment(self, appointment_id: str) -> bool:
        """Удаляет запись из БД и из Google Calendar."""

        # --- Сначала получаем запись, чтобы получить google_event_id ---
        appointment = await self.get_appointment_by_id(appointment_id)

        if not appointment:
            logger.warning(f"Не удалось найти запись с ID {appointment_id} для удаления.")
            return False

        # --- СИНХРОНИЗАЦИЯ С GOOGLE CALENDAR ---
        # Если у записи есть google_event_id, пытаемся удалить соответствующее событие
        if appointment.google_event_id:
            # --- ВЫЗОВ ФУНКЦИИ УДАЛЕНИЯ ---
            if not utils.google_calendar.delete_google_calendar_event(appointment.google_event_id):
                logger.warning(
                    f"Не удалось удалить событие Google Calendar '{appointment.google_event_id}' для записи '{appointment_id}'.")
            else:
                logger.info(
                    f"Событие Google Calendar '{appointment.google_event_id}' для записи '{appointment_id}' успешно удалено.")
        else:
            logger.info(
                f"Запись '{appointment_id}' не имеет Google Event ID, поэтому удаление из Google Calendar пропускается.")

        # --- УДАЛЕНИЕ ИЗ БД ---
        try:
            # Формируем запрос на удаление.
            query_builder = self.client.table('appointments').delete().eq('id', appointment_id)

            # --- ИСПРАВЛЕНИЕ: Вызов синхронного execute через asyncio.to_thread ---
            # Предполагаем, что execute() синхронный, а вызывается в async методе.
            response = await asyncio.to_thread(query_builder.execute)
            # ---

            if response and response.data and len(response.data) > 0:
                logger.info(f"Запись '{appointment_id}' успешно удалена.")
                return True
            else:
                logger.warning(f"Удаление записи '{appointment_id}' не дало результата (запись не найдена?).")
                return False
        except Exception as e:
            logger.error(f"Error deleting appointment id {appointment_id}: {e}", exc_info=True)
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
            # --- ИСПРАВЛЕНИЕ: Вызов синхронного execute через asyncio.to_thread ---
            query_builder = self.client.table('appointments').update(
                {'google_event_id': google_event_id}
            ).eq('id', appointment_id)
            response = await asyncio.to_thread(query_builder.execute)  # <-- Без await на execute, но await на to_thread
            # ---

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