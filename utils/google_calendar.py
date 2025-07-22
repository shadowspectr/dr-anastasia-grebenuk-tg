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

def create_google_calendar_event(appointment_time_str: str, service_title: str, client_name: str,
                                 client_phone: Optional[str] = None, service_duration_minutes: int = 60) -> Optional[str]:
    """
    Создает событие в Google Calendar и возвращает ID созданного события.

    Args:
        appointment_time_str (str): Время записи в формате "YYYY-MM-DD HH:MM".
        service_title (str): Название услуги.
        client_name (str): Имя клиента.
        client_phone (Optional[str]): Номер телефона клиента.
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

        # Формируем описание события, включая номер телефона, если он есть
        description_lines = [
            f'Запись для клиента: {client_name}',
            f'Услуга: {service_title}'
        ]
        if client_phone:
            description_lines.append(f'Телефон: {client_phone}')

        event = {
            'summary': f'{service_title} - {client_name}',
            'description': '\n'.join(description_lines),
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

def update_google_calendar_event(event_id: str, appointment_time_str: str, service_title: str, client_name: str, client_phone: Optional[str] = None, service_duration_minutes: int = 60):
    """
    Обновляет существующее событие в Google Calendar.

    Args:
        event_id (str): ID события Google Calendar.
        appointment_time_str (str): Новое время записи в формате "YYYY-MM-DD HH:MM".
        service_title (str): Новое название услуги.
        client_name (str): Новое имя клиента.
        client_phone (Optional[str]): Новый номер телефона клиента.
        service_duration_minutes (int): Новая продолжительность услуги (по умолчанию 60).

    Returns:
        bool: True, если событие успешно обновлено, False в противном случае.
    """
    service = get_google_calendar_service()
    if not service:
        return False
    if not event_id:
        logger.warning("Невозможно обновить событие: отсутствует event_id.")
        return False

    try:
        appointment_dt = datetime.strptime(appointment_time_str, '%Y-%m-%d %H:%M')
        end_time_dt = appointment_dt + timedelta(minutes=service_duration_minutes)

        description_lines = [
            f'Запись для клиента: {client_name}',
            f'Услуга: {service_title}'
        ]
        if client_phone:
            description_lines.append(f'Телефон: {client_phone}')

        event = {
            'summary': f'{service_title} - {client_name}',
            'description': '\n'.join(description_lines),
            'start': {'dateTime': appointment_dt.isoformat(), 'timeZone': 'Europe/Moscow'}, # <-- Укажите ваш часовой пояс!
            'end': {'dateTime': end_time_dt.isoformat(), 'timeZone': 'Europe/Moscow'},   # <-- Укажите ваш часовой пояс!
            'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 1440}]},
        }

        updated_event = service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=event).execute()
        logger.info(f"Событие Google Calendar с ID '{event_id}' обновлено: {updated_event.get('htmlLink')}")
        return True

    except HttpError as error:
        logger.error(f'Произошла ошибка Google API при обновлении события: {error}')
        if error.resp.status == 404:
            logger.error(f"Событие с ID '{event_id}' не найдено в календаре '{CALENDAR_ID}'. Возможно, оно было удалено вручную.")
        return False
    except Exception as e:
        logger.error(f'Произошла непредвиденная ошибка при обновлении события Google Calendar: {e}')
        return False


def delete_google_calendar_event(event_id: str):
    """
    Удаляет событие из Google Calendar.

    Args:
        event_id (str): ID события Google Calendar.

    Returns:
        bool: True, если событие успешно удалено, False в противном случае.
    """
    service = get_google_calendar_service()
    if not service:
        return False
    if not event_id:
        logger.warning("Невозможно удалить событие: отсутствует event_id.")
        return False

    try:
        # --- ВАЖНО: execute() здесь тоже может быть синхронным ---
        # Если библиотека работает так, что execute() для delete тоже синхронный,
        # то его тоже нужно будет обернуть в asyncio.to_thread.
        # Однако, методы delete() и update() могут вести себя иначе.
        # Попробуем сначала без asyncio.to_thread.

        # --- Попробуем без asyncio.to_thread ---
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
        logger.info(f"Событие Google Calendar с ID '{event_id}' успешно удалено.")
        return True
        # --- Если будет ошибка, то нужно будет попробовать: ---
        # await asyncio.to_thread(service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute)
        # Но в данном случае, delete() может быть методом, который сам возвращает результат,
        # а execute() уже его выполняет.

    except HttpError as error:
        logger.error(f'Произошла ошибка Google API при удалении события: {error}')
        if error.resp.status == 404:
            logger.error(
                f"Событие с ID '{event_id}' не найдено в календаре '{CALENDAR_ID}'. Возможно, оно было удалено вручную.")
        return False
    except Exception as e:
        logger.error(f'Произошла непредвиденная ошибка при удалении события Google Calendar: {e}')
        return False