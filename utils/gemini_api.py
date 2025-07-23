# utils/gemini_api.py

import os
import google.generativeai as genai
import logging
from typing import Optional, List

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


async def generate_text(prompt: str, model_name: str = "gemini-2.0-flash-thinking-exp-01-21", max_chars_per_message: int = 4000) -> Optional[
    List[str]]:
    """
    Отправляет запрос к Gemini API, разбивает ответ на части, если он длинный,
    и возвращает список строк. Предполагается, что Gemini API возвращает Markdown.
    """
    model = get_gemini_model(model_name)
    if not model:
        return None

    try:
        response = await model.generate_content_async(prompt)

        if not response or not response.text:
            logger.warning("Gemini API вернул пустой ответ или не удалось получить текст.")
            return None

        full_text = response.text

        if len(full_text) > max_chars_per_message:
            parts = []
            current_pos = 0

            # Попытка разбить по переносу строки или пробелу, чтобы сохранить форматирование
            while current_pos < len(full_text):
                end_pos = min(current_pos + max_chars_per_message, len(full_text))

                # Ищем последний символ новой строки или пробела перед end_pos
                split_point = -1
                if end_pos < len(full_text):  # Если не конец текста
                    # Ищем символ новой строки (\n)
                    nl_split = full_text.rfind('\n', current_pos, end_pos)
                    if nl_split != -1:
                        split_point = nl_split
                    else:
                        # Если нет переноса строки, ищем последний пробел
                        sp_split = full_text.rfind(' ', current_pos, end_pos)
                        if sp_split != -1:
                            split_point = sp_split

                if split_point == -1 or split_point == current_pos:  # Если не нашли подходящий разделитель
                    split_point = end_pos  # Разделяем по символам

                part = full_text[current_pos:split_point]
                parts.append(part.strip())  # Удаляем лишние пробелы в начале/конце части

                current_pos = split_point + 1  # Переходим к следующему символу после разделения

            logger.info(f"Response was split into {len(parts)} parts.")
            return parts
        else:
            return [full_text]

    except Exception as e:
        logger.error(f"Ошибка при обращении к Gemini API: {e}")
        return None
