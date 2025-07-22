import logging
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

# Получаем пути к файлам из переменных окружения или напрямую
# Предполагается, что credentials.json находится в корне проекта,
# а google_calendar_id в .env файле
SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = 'credentials.json'
CALENDAR_ID = os.environ.get('GOOGLE_CALENDAR_ID') # Получаем ID календаря из .env

logger = logging.getLogger(__name__)

def get_credentials():
    """Загружает или создает учетные данные Google API."""
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        except Exception as e:
            logger.error(f"Ошибка загрузки token.json: {e}")
            # Если token.json поврежден или устарел, удаляем его и пересоздаем
            os.remove('token.json')
            return get_credentials()
    else:
        creds = None

    # Если нет учетных данных или они недействительны
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Ошибка обновления токена: {e}")
                # Если обновление не удалось, удаляем token.json
                if os.path.exists('token.json'):
                    os.remove('token.json')
                creds = None # Сбрасываем creds, чтобы начать процесс авторизации заново
        else:
            # Если нет токена, запускаем процесс установки
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                # Здесь может потребоваться изменить следующий вызов в зависимости от того,
                # где выполняется ваш код. Для локального запуска `run_local_server()` обычно подходит.
                # Если бот развернут на сервере, может потребоваться другой подход.
                creds = flow.run_local_server(port=0)
            except FileNotFoundError:
                logger.error(f"Файл {CREDENTIALS_FILE} не найден. Убедитесь, что он существует.")
                return None
            except Exception as e:
                logger.error(f"Ошибка при запуске авторизации: {e}")
                return None

        # Сохраняем учетные данные для следующего запуска
        if creds:
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
    return creds

def create_google_calendar_event(appointment_time_str: str, service_title: str, client_name: str, service_duration_minutes: int = 60):
    """
    Создает событие в Google Calendar.

    Args:
        appointment_time_str (str): Время записи в формате "YYYY-MM-DD HH:MM".
        service_title (str): Название услуги.
        client_name (str): Имя клиента.
        service_duration_minutes (int): Продолжительность услуги в минутах (по умолчанию 60).

    Returns:
        bool: True, если событие успешно создано, False в противном случае.
    """
    if not CALENDAR_ID:
        logger.error("GOOGLE_CALENDAR_ID не установлен в переменных окружения.")
        return False

    creds = get_credentials()
    if not creds:
        logger.error("Не удалось получить учетные данные Google API.")
        return False

    try:
        service = build('calendar', 'v3', credentials=creds)

        # Парсим время записи
        appointment_dt = datetime.strptime(appointment_time_str, '%Y-%m-%d %H:%M')
        end_time_dt = appointment_dt + timedelta(minutes=service_duration_minutes)

        event = {
            'summary': f'{service_title} - {client_name}',
            'description': f'Запись для клиента: {client_name}\nУслуга: {service_title}',
            'start': {
                'dateTime': appointment_dt.isoformat(),
                'timeZone': 'Europe/Moscow', # Укажите ваш часовой пояс
            },
            'end': {
                'dateTime': end_time_dt.isoformat(),
                'timeZone': 'Europe/Moscow', # Укажите ваш часовой пояс
            },
            'attendees': [
                {'email': 'admin@example.com'}, # Можно добавить email администратора, если он известен
            ],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 1440}, # Напоминание за 1 день (24 часа)
                ],
            },
        }

        created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        logger.info(f"Событие Google Calendar создано: {created_event.get('htmlLink')}")
        return True

    except HttpError as error:
        logger.error(f'Произошла ошибка Google API: {error}')
        # Обработка специфических ошибок, например, невалидных данных
        return False
    except Exception as e:
        logger.error(f'Произошла непредвиденная ошибка при создании события Google Calendar: {e}')
        return False