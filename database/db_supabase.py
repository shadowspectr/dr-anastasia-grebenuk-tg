# database/db_supabase.py

import logging
from typing import List, Optional
from dataclasses import asdict
from datetime import datetime, time, timedelta

# Импортируем и AsyncClient, и APIResponse для отладки
from supabase import AsyncClient, create_client
from postgrest import APIResponse # <-- Исправленный импорт
from .models import Appointment, Service, ServiceCategory

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, async_client: AsyncClient):
        # Принимаем уже готовый асинхронный клиент
        self.async_client = async_client
        logger.info(
            f"Database initialized with client type: {type(self.async_client)}")  # Логируем тип клиента при инициализации

    # --- Методы для Услуг и Категорий ---

    async def get_service_categories(self) -> List[ServiceCategory]:
        logger.debug("Attempting to get service categories...")
        logger.debug(f"Client type inside method: {type(self.async_client)}")  # Логируем тип клиента внутри метода
        try:
            # --- ОТЛАДОЧНЫЕ ЛОГИ ---
            table_ref = self.async_client.from_('service_categories')
            logger.debug(f"from_('...'). Type: {type(table_ref)}")  # Логируем тип после from_

            select_ref = table_ref.select('*').order('title')
            logger.debug(f"select('*').order(...). Type: {type(select_ref)}")  # Логируем тип после select и order

            # ЭТО СТРОКА, КОТОРАЯ ВЫЗЫВАЕТ ОШИБКУ APIResponse
            response_coroutine = select_ref.execute()
            logger.debug(f"execute(). Type: {type(response_coroutine)}")  # Логируем тип того, что вернул execute()

            # Этот await вызывает ошибку, если response_coroutine не является корутиной
            response: APIResponse = await response_coroutine
            # --- КОНЕЦ ОТЛАДОЧНЫХ ЛОГОВ ---

            logger.debug(f"Successfully received response. Type: {type(response)}. Data: {response.data}")

            return [ServiceCategory(**row) for row in response.data] if response.data else []
        except Exception as e:
            logger.error(f"Error getting service categories. Error type: {type(e).__name__}. Error: {e}")
            return []

    # ... (Остальные методы класса Database без изменений, как в Re-Refactored v4) ...
    # Вам нужно будет убедиться, что они используют await ... .execute() синтаксис
    # Я скопирую их ниже для полноты, но без дополнительных отладочных логов

    async def get_services_by_category(self, category_id: str) -> List[Service]:
        try:
            response = await self.async_client.from_('services').select('*').eq('category_id', category_id).order(
                'title').execute()
            return [Service(**row) for row in response.data] if response.data else []
        except Exception as e:
            logger.error(f"Error getting services by category. Error type: {type(e).__name__}. Error: {e}")
            return []

    async def get_service_by_id(self, service_id: str) -> Optional[Service]:
        try:
            response = await self.async_client.from_('services').select('*').eq('id', service_id).limit(
                1).single().execute()
            return Service(**response.data) if response.data else None
        except Exception as e:
            logger.error(f"Error getting service by id. Error type: {type(e).__name__}. Error: {e}")
            return None

    async def add_appointment(self, appointment: Appointment) -> Optional[str]:
        appointment_dict = asdict(appointment)
        for key in ['id', 'created_at', 'service_title']:
            appointment_dict.pop(key, None)
        if isinstance(appointment.appointment_time, datetime):
            appointment_dict['appointment_time'] = appointment.appointment_time.isoformat()

        try:
            response = await self.async_client.from_('appointments').insert(appointment_dict).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error adding appointment. Error type: {type(e).__name__}. Error: {e}")
            return None

    async def delete_appointment(self, app_id: str) -> bool:
        try:
            response = await self.async_client.from_('appointments').delete().eq('id', app_id).execute()
            logger.info(f"Successfully deleted appointment from DB with id: {app_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting appointment by id. Error type: {type(e).__name__}. Error: {e}")
            return False

    async def update_appointment_status(self, app_id: str, status: str):
        try:
            await self.async_client.from_('appointments').update({'status': status}).eq('id', app_id).execute()
        except Exception as e:
            logger.error(f"Error updating appointment status. Error type: {type(e).__name__}. Error: {e}")

    async def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        tomorrow = datetime.now() + timedelta(days=1)
        start_of_day = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

        try:
            query = self.async_client.from_('appointments').select('*, services(title)') \
                .gte('appointment_time', start_of_day) \
                .lte('appointment_time', end_of_day) \
                .eq('status', 'active') \
                .set_query('reminded', 'is', 'false')  # Уточнение для boolean 'is' false

            response = await query.order('appointment_time').execute()
            if not response.data: return []

            appointments = []
            for row in response.data:
                service_data = row.pop('services', None)
                if row.get('appointment_time'):
                    try:
                        row['appointment_time'] = datetime.fromisoformat(row['appointment_time'])
                    except ValueError:
                        row['appointment_time'] = datetime.strptime(row['appointment_time'].split('.')[0],
                                                                    '%Y-%m-%dT%H:%M:%S')
                else:
                    continue

                app = Appointment(**row)
                app.service_title = service_data['title'] if service_data else "Удаленная услуга"
                appointments.append(app)
            return appointments
        except Exception as e:
            logger.error(f"Error getting upcoming appointments to remind. Error type: {type(e).__name__}. Error: {e}")
            return []

    async def mark_as_reminded(self, appointment_id: str):
        try:
            await self.async_client.from_('appointments').update({'reminded': True}).eq('id', appointment_id).execute()
        except Exception as e:
            logger.error(f"Error marking appointment as reminded. Error type: {type(e).__name__}. Error: {e}")

    async def get_appointments_for_day(self, target_date: datetime) -> List[Appointment]:
        start_of_day = datetime.combine(target_date.date(), time.min).isoformat()
        end_of_day = datetime.combine(target_date.date(), time.max).isoformat()

        try:
            query = self.async_client.from_('appointments').select('*, services(title)').gte('appointment_time',
                                                                                             start_of_day).lte(
                'appointment_time', end_of_day).order('appointment_time')

            response = await query.execute()
            if not response.data: return []

            appointments = []
            for row in response.data:
                service_data = row.pop('services', None)
                if row.get('appointment_time'):
                    try:
                        row['appointment_time'] = datetime.fromisoformat(row['appointment_time'])
                    except ValueError:
                        row['appointment_time'] = datetime.strptime(row['appointment_time'].split('.')[0],
                                                                    '%Y-%m-%dT%H:%M:%S')
                else:
                    continue
                app = Appointment(**row)
                app.service_title = service_data['title'] if service_data else "Удаленная услуга"
                appointments.append(app)
            return appointments
        except Exception as e:
            logger.error(f"Error getting appointments for day. Error type: {type(e).__name__}. Error: {e}")
            return []

    async def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        try:
            response = await self.async_client.from_('appointments').select('*, services(title)').eq('id',
                                                                                                     appointment_id).limit(
                1).single().execute()
            if not response.data: return None

            row = response.data
            service_data = row.pop('services', None)
            if row.get('appointment_time'):
                try:
                    row['appointment_time'] = datetime.fromisoformat(row['appointment_time'])
                except ValueError:
                    row['appointment_time'] = datetime.strptime(row['appointment_time'].split('.')[0],
                                                                '%Y-%m-%dT%H:%M:%S')

            app = Appointment(**row)
            app.service_title = service_data['title'] if service_data else "Удаленная услуга"
            return app
        except Exception as e:
            logger.error(f"Error getting appointment by id. Error type: {type(e).__name__}. Error: {e}")
            return None