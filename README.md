Local LM Arena (Extended)

Инструмент для сравнения локальных языковых моделей (LLM) через LM Studio. Система позволяет проводить слепое тестирование, вычислять рейтинг Elo и экспортировать результаты в JSON.

Возможности

Слепое тестирование: Имена моделей скрыты до момента голосования.

Рейтинг Elo: Автоматический пересчет рейтинга после каждой битвы.

Экспорт данных: Сохранение истории тестов (вопрос, ответы, коррекция Elo) в arena_history.json.

Авто-вопросы: Генерация случайных промптов одной из загруженных моделей.

Поддержка LM Studio: Прямая интеграция с локальным сервером.

Структура проекта

arena.py: Flask-сервер и фронтенд в одном файле.

arena_history.json: База данных результатов тестов.

requirements.txt: Список необходимых библиотек.

Установка и запуск

Клонируйте репозиторий:

git clone [https://github.com/vash-user/local-lm-arena.git](https://github.com/vash-user/local-lm-arena.git)
cd local-lm-arena


Создайте виртуальное окружение:

python -m venv venv
source venv/bin/activate  # Для Windows: venv\Scripts\activate


Установите зависимости:

pip install -r requirements.txt


Настройте LM Studio:

Запустите LM Studio.

Перейдите в раздел Local Server.

Загрузите минимум 2 модели.

Нажмите Start Server.

Запустите арену:

python arena.py


Откройте в браузере: http://localhost:5010

Работа с моделями через терминал (CLI)

Если у вас установлен CLI инструмент от LM Studio (lms), вы можете управлять моделями прямо из терминала:

Посмотреть доступные модели:

lms ls


Загрузить конкретную модель в память:

lms load "название-модели"


Выгрузить все модели:

lms unload --all


Проверить статус сервера:

lms status


Формат экспорта данных

Результаты тестов сохраняются в arena_history.json. Пример записи:

{
  "question": "Как центрировать div?",
  "models": { "left": "llama-3", "right": "gemma-2" },
  "outcome": "left",
  "elo_correction": { "delta": 16.0, "ew_after": 1016.0 }
}


<img width="1143" height="693" alt="image" src="https://github.com/user-attachments/assets/30c285c6-151d-4980-9824-d44716000014" />
