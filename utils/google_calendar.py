import logging
from datetime import datetime, timedelta, time
import os
from typing import List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource

logger = logging.getLogger(__name__)

# --- Настройки ---
# Путь к JSON-ключу, который мы загрузили как Secret File
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'credentials.json'

# ID календаря, который вы получили на Шаге 1
# Лучше вынести его в переменные окружения (.env и на Render)
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")


class GoogleCalendar:
    """Класс для взаимодействия с Google Calendar API."""
    _service: Optional[Resource] = None

    @classmethod
    def _get_service(cls) -> Optional[Resource]:
        """
        Инициализирует и возвращает сервис для работы с API.
        Использует паттерн Singleton для одного экземпляра.
        """
        if cls._service is None:
            try:
                creds = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
                cls._service = build('calendar', 'v3', credentials=creds)
                logger.info("Successfully connected to Google Calendar API.")
            except Exception as e:
                logger.error(f"Failed to connect to Google Calendar API: {e}")
                return None
        return cls._service

    @classmethod
    async def add_appointment(cls, client_name: str, service_title: str, appointment_time: datetime, phone_number: str,
                              duration_minutes: int = 60) -> Optional[str]:
        """
        Добавляет новое событие (запись) в календарь.
        Включает номер телефона в описание.
        Возвращает ID созданного события.
        """
        service = cls._get_service()
        if not service:
            return None

        start_time = appointment_time.isoformat()
        end_time = (appointment_time + timedelta(minutes=duration_minutes)).isoformat()

        event = {
            'summary': f'{client_name} - {service_title}',
            # Добавляем телефон в описание события
            'description': f'Запись на услугу: {service_title}\n\nТелефон для связи: {phone_number}',
            'start': {
                'dateTime': start_time,
                'timeZone': 'Europe/Moscow',  # Важно указать ваш часовой пояс
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Europe/Moscow',
            },
        }

        try:
            created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            event_id = created_event.get('id')
            logger.info(f"Event created in Google Calendar with ID: {event_id}")
            return event_id
        except Exception as e:
            logger.error(f"Failed to create event in Google Calendar: {e}")
            return None

    @classmethod
    async def get_busy_slots(cls, target_date: datetime) -> List[datetime]:
        """
        Получает список начала всех занятых слотов на указанную дату.
        """
        service = cls._get_service()
        if not service:
            return []

        start_of_day = datetime.combine(target_date.date(), time.min).isoformat() + 'Z'  # 'Z' означает UTC
        end_of_day = datetime.combine(target_date.date(), time.max).isoformat() + 'Z'

        try:
            events_result = service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=start_of_day,
                timeMax=end_of_day,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            busy_times = []
            for event in events:
                start_str = event['start'].get('dateTime')
                if start_str:
                    # Преобразуем строку UTC в объект datetime
                    busy_times.append(datetime.fromisoformat(start_str.replace('Z', '+00:00')))
            return busy_times
        except Exception as e:
            logger.error(f"Failed to get events from Google Calendar: {e}")
            return []