import logging
from typing import List, Optional, Dict, Any
from dataclasses import asdict
from datetime import datetime, time, timedelta

from supabase import create_client, Client as SupabaseConnection
from .models import Appointment, Service, ServiceCategory

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, key: str):
        self.client: SupabaseConnection = create_client(url, key)

    def _execute_query(self, query) -> (Optional[List[Dict[str, Any]]], Optional[str]):
        try:
            response = query.execute()
            return response.data, None
        except Exception as e:
            logger.error(f"Supabase query failed: {e}")
            return None, str(e)

    def get_service_categories(self) -> List[ServiceCategory]:
        data, error = self._execute_query(self.client.table('service_categories').select('*').order('title'))
        if error or not data: return []
        return [ServiceCategory(**row) for row in data]

    def get_services_by_category(self, category_id: str) -> List[Service]:
        data, error = self._execute_query(
            self.client.table('services').select('*').eq('category_id', category_id).order('title'))
        if error or not data: return []
        return [Service(**row) for row in data]

    def get_service_by_id(self, service_id: str) -> Optional[Service]:
        data, error = self._execute_query(self.client.table('services').select('*').eq('id', service_id).limit(1))
        if error or not data: return None
        return Service(**data[0])

    def add_appointment(self, appointment: Appointment) -> Optional[str]:
        appointment_dict = asdict(appointment)
        # Убираем поля, которые не должны идти в insert
        for key in ['id', 'created_at', 'service_title']:
            appointment_dict.pop(key, None)
        appointment_dict['appointment_time'] = appointment.appointment_time.isoformat()

        data, error = self._execute_query(self.client.table('appointments').insert(appointment_dict).select('id'))
        if error or not data: return None
        return data[0]['id']

    def get_appointments_for_day(self, target_date: datetime, status: str = 'active') -> List[Appointment]:
        start_of_day = datetime.combine(target_date.date(), time.min).isoformat()
        end_of_day = datetime.combine(target_date.date(), time.max).isoformat()

        query = self.client.table('appointments').select('*, services(title)').gte('appointment_time',
                                                                                   start_of_day).lte('appointment_time',
                                                                                                     end_of_day).order(
            'appointment_time')
        if status:
            query = query.eq('status', status)

        data, error = self._execute_query(query)
        if error or not data: return []

        appointments = []
        for row in data:
            service_data = row.pop('services', None)
            app = Appointment(**row)
            app.service_title = service_data['title'] if service_data else "Удаленная услуга"
            appointments.append(app)
        return appointments

    def get_upcoming_appointments_to_remind(self) -> List[Appointment]:
        tomorrow_start = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0,
                                                                      microsecond=0).isoformat()
        tomorrow_end = (datetime.now() + timedelta(days=1)).replace(hour=23, minute=59, second=59,
                                                                    microsecond=999999).isoformat()

        query = self.client.table('appointments').select('*, services(title)').gte('appointment_time',
                                                                                   tomorrow_start).lte(
            'appointment_time', tomorrow_end).eq('status', 'active').eq('reminded', False)
        data, error = self._execute_query(query)
        if error or not data: return []

        appointments = []
        for row in data:
            service_data = row.pop('services', None)
            app = Appointment(**row)
            app.service_title = service_data['title'] if service_data else "Удаленная услуга"
            appointments.append(app)
        return appointments

    def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        data, error = self._execute_query(
            self.client.table('appointments').select('*, services(title)').eq('id', appointment_id).limit(1))
        if error or not data: return None

        row = data[0]
        service_data = row.pop('services', None)
        app = Appointment(**row)
        app.service_title = service_data['title'] if service_data else "Удаленная услуга"
        return app

    def mark_as_reminded(self, appointment_id: str):
        self._execute_query(self.client.table('appointments').update({'reminded': True}).eq('id', appointment_id))

    def update_appointment_status(self, appointment_id: str, status: str):
        self._execute_query(self.client.table('appointments').update({'status': status}).eq('id', appointment_id))

    def delete_appointment(self, appointment_id: str) -> bool:
        data, error = self._execute_query(
            self.client.table('appointments').delete().eq('id', appointment_id).select('id'))
        return not error and data is not None