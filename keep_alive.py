# keep_alive.py
import logging
from flask import Flask
from threading import Thread

# Устанавливаем базовый уровень логирования для Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask('app')


@app.route('/')
def main_route():
    return "I'm alive!"


def run():
    # Render.com предоставляет порт в переменной окружения PORT
    # Если ее нет, используем 8080 для локального запуска
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    """Запускает веб-сервер в отдельном потоке."""
    server = Thread(target=run)
    server.start()