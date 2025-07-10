# Шаг 1: Используем официальный образ Python 3.11
FROM python:3.11-slim

# Шаг 2: Устанавливаем системные зависимости и компилятор Rust (cargo)
# Это ключевой шаг, который решает проблему.
RUN apt-get update && apt-get install -y --no-install-recommends curl gcc && \
    curl https://sh.rustup.rs -sSf | sh -s -- -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Добавляем Rust в системную переменную PATH, чтобы pip мог его найти
ENV PATH="/root/.cargo/bin:${PATH}"

# Шаг 3: Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Шаг 4: Копируем только файл с зависимостями
COPY requirements.txt .

# Шаг 5: Устанавливаем зависимости. Теперь pip найдет Rust и все скомпилирует.
RUN pip install --no-cache-dir -r requirements.txt

# Шаг 6: Копируем весь остальной код нашего проекта
COPY . .

# Шаг 7: Указываем команду, которая будет запущена при старте контейнера
CMD ["python", "main.py"]