# utils/google_calendar.py

import logging
from datetime import datetime, timedelta
from typing import Optional # <-- ДОБАВЛЕНО
# Импорт для сервисных аккаунтов
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

# Имя файла ключа сервисного аккаунта.
# Убедись, что этот файл находится в корневой папке вашего проекта.
# Если он называется иначе (например, credentials.json), измените это имя.
SERVICE_ACCOUNT_FILE = 'credentials.json' # <-- Убедитесь, что это правильное имя файла!
SCOPES = ['https://www.googleapis.com/auth/calendar'] # Скоупы для доступа к календарю

# Получаем ID календаря из переменных окружения (например, из .env файла)
CALENDAR_ID = os.environ.get('GOOGLE_CALENDAR_ID')

logger = logging.getLogger(__name__)

def get_google_calendar_service():
    """
    Создает и возвращает объект сервиса Google Calendar, используя сервисный аккаунт.
    """
    if not CALENDAR_ID:
        logger.error("GOOGLE_CALENDAR_ID не установлен в переменных окружения.")
        return None

    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        logger.error(f"Файл ключа сервисного аккаунта '{SERVICE_ACCOUNT_FILE}' не найден. "
                     f"Убедитесь, что он существует в корне проекта.")
        return None

    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
        logger.info("Успешно подключено к Google Calendar через сервисный аккаунт.")
        return service

    except FileNotFoundError:
        logger.error(f"Файл ключа сервисного аккаунта '{SERVICE_ACCOUNT_FILE}' не найден.")
        return None
    except Exception as e:
        logger.error(f"Ошибка при подключении к Google Calendar: {e}")
        return None

def create_google_calendar_event(appointment_time_str: str, service_title: str, client_name: str, service_duration_minutes: int = 60) -> Optional[str]:
    """
    Создает событие в Google Calendar и возвращает ID созданного события.

    Args:
        appointment_time_str (str): Время записи в формате "YYYY-MM-DD HH:MM".
        service_title (str): Название услуги.
        client_name (str): Имя клиента.
        service_duration_minutes (int): Продолжительность услуги в минутах (по умолчанию 60).

    Returns:
        Optional[str]: ID созданного события Google Calendar в случае успеха, иначе None.
    """
    service = get_google_calendar_service()
    if not service:
        return None

    try:
        appointment_dt = datetime.strptime(appointment_time_str, '%Y-%m-%d %H:%M')
        end_time_dt = appointment_dt + timedelta(minutes=service_duration_minutes)

        event = {
            'summary': f'{service_title} - {client_name}',
            'description': f'Запись для клиента: {client_name}\nУслуга: {service_title}',
            'start': {'dateTime': appointment_dt.isoformat(), 'timeZone': 'Europe/Moscow'}, # <-- Укажите ваш часовой пояс!
            'end': {'dateTime': end_time_dt.isoformat(), 'timeZone': 'Europe/Moscow'},   # <-- Укажите ваш часовой пояс!
            'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 1440}]},
        }

        created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        event_id = created_event.get('id')
        logger.info(f"Событие Google Calendar создано: {created_event.get('htmlLink')}")
        return event_id

    except HttpError as error:
        logger.error(f'Произошла ошибка Google API: {error}')
        if error.resp.status == 404:
            logger.error(f"Календарь с ID '{CALENDAR_ID}' не найден. Проверьте правильность GOOGLE_CALENDAR_ID.")
        return None
    except Exception as e:
        logger.error(f'Произошла непредвиденная ошибка при создании события Google Calendar: {e}')
        return None