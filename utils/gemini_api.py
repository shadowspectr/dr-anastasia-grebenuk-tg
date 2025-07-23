# utils/gemini_api.py

import os
import google.generativeai as genai
import logging
from typing import Optional

# Получаем API ключ из переменных окружения
API_KEY = os.getenv('GOOGLE_API_KEY')

logger = logging.getLogger(__name__)

# Конфигурируем API ключ
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    logger.error("GOOGLE_API_KEY не установлен. Интеграция с Gemini API невозможна.")


def get_gemini_model(model_name: str = "gemini-2.0-flash-thinking-exp-01-21"):
    """
    Возвращает сконфигурированную модель Gemini.
    """
    if not API_KEY:
        return None
    try:
        model = genai.GenerativeModel(model_name)
        return model
    except Exception as e:
        logger.error(f"Не удалось получить модель Gemini ({model_name}): {e}")
        return None


async def generate_text(prompt: str, model_name: str = "gemini-2.0-flash-thinking-exp-01-21") -> Optional[str]:
    """
    Отправляет запрос к Gemini API и возвращает сгенерированный текст.

    Args:
        prompt (str): Текст запроса к модели.
        model_name (str): Название модели (по умолчанию "gemini-pro").

    Returns:
        Optional[str]: Сгенерированный текст или None в случае ошибки.
    """
    model = get_gemini_model(model_name)
    if not model:
        return None

    try:
        # Запускаем генерацию текста
        # Для Gemini API v1.0, это response = model.generate_content(prompt)
        # Для Gemini API v1.5 (или более поздних), может быть chat.send_message()
        # Учитывая, что мы делаем "text generation", будем использовать generate_content

        # Важно: generate_content - это асинхронная функция, ее нужно await'ить
        response = await model.generate_content_async(prompt)

        # Проверяем, есть ли текст в ответе
        if response and response.text:
            return response.text
        else:
            logger.warning("Gemini API вернул пустой ответ или не удалось получить текст.")
            return None

    except Exception as e:
        logger.error(f"Ошибка при обращении к Gemini API: {e}")
        return None
