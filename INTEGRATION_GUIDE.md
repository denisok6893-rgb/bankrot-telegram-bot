# Руководство по интеграции модуля "Карточки дел"

## Обзор

Модуль "Карточки дел" реализует CRUD-функционал для управления делами о банкротстве через Telegram-бота.

## Установленные компоненты

### 1. База данных (PostgreSQL + SQLAlchemy)

**Файлы:**
- `bankrot_bot/database.py` - конфигурация подключения к БД
- `bankrot_bot/models/case.py` - модель Case
- `alembic/` - директория миграций Alembic
- `alembic.ini` - конфигурация Alembic
- `alembic/versions/20260112_0000_001_create_cases_table.py` - миграция создания таблицы

**Модель Case:**
```python
- id: int (PK)
- user_id: int (Telegram user ID)
- debtor_name: str (имя должника)
- debtor_inn: str | None (ИНН)
- case_number: str | None (номер дела)
- court: str | None (наименование суда)
- stage: CaseStage | None (стадия банкротства)
- manager_name: str | None (арбитражный управляющий)
- created_at: datetime
- updated_at: datetime
```

**Стадии дела (CaseStage):**
- OBSERVATION - "наблюдение"
- RESTRUCTURING - "реструктуризация"
- REALIZATION - "реализация"
- COMPLETED - "завершено"

### 2. Хендлеры (aiogram)

**Файл:** `bankrot_bot/handlers/cases.py`

**Реализованные команды:**

1. `/newcase` - создание нового дела (FSM, пошаговый ввод)
   - Поля: имя должника, ИНН, номер дела, суд, стадия, АУ
   - После создания автоматически устанавливается как активное

2. `/mycases` - список всех дел пользователя
   - Показывает до 50 последних дел
   - Сортировка по дате обновления

3. `/case <id>` - просмотр карточки дела
   - Красивое форматирование с эмодзи
   - Вся информация о деле

4. `/setactive <id>` - установить активное дело
   - Сохраняется в FSM state (Redis)
   - Используется для команды /editcase

5. `/editcase` - редактирование активного дела
   - Редактирование любого поля
   - FSM для выбора поля и ввода значения

6. `/cancel` - отмена текущей операции (сохраняет active_case_id)

### 3. Redis

**Docker Compose:**
- Добавлен сервис `redis`
- Хранит FSM состояния и active_case_id
- Переменная окружения: `REDIS_URL`

### 4. Зависимости

**Файл:** `requirements.txt`

Добавлены:
- sqlalchemy>=2.0.0
- asyncpg>=0.29.0
- psycopg2-binary>=2.9.0
- alembic>=1.13.0
- redis>=5.0.0
- aioredis>=2.0.0

## Интеграция в bot.py

### Шаг 1: Импорты

Добавьте в начало `bot.py`:

```python
import os
from aiogram.fsm.storage.redis import RedisStorage

# Database
from bankrot_bot.database import init_db
from bankrot_bot.handlers import cases as cases_handlers
```

### Шаг 2: Настройка Redis Storage

Замените создание диспетчера:

```python
# Было:
dp = Dispatcher()

# Стало:
# Configure Redis storage for FSM
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
storage = RedisStorage.from_url(redis_url)
dp = Dispatcher(storage=storage)
```

### Шаг 3: Регистрация роутера

Добавьте после создания диспетчера:

```python
# Register cases router
dp.include_router(cases_handlers.router)
```

### Шаг 4: Инициализация БД

Добавьте в функцию запуска бота (перед `dp.start_polling`):

```python
async def main():
    """Start the bot."""
    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # ... остальной код ...

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
```

### Полный пример интеграции:

```python
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from bankrot_bot.config import load_settings
from bankrot_bot.logging_setup import setup_logging
from bankrot_bot.database import init_db
from bankrot_bot.handlers import cases as cases_handlers

setup_logging()
logger = logging.getLogger(__name__)

async def main():
    """Start the bot."""
    settings = load_settings()
    bot = Bot(token=settings["BOT_TOKEN"])

    # Configure Redis storage
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    storage = RedisStorage.from_url(redis_url)
    dp = Dispatcher(storage=storage)

    # Register routers
    dp.include_router(cases_handlers.router)
    # ... другие роутеры ...

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    logger.info("Starting bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
```

## Запуск миграций

### Вариант 1: Из контейнера

```bash
docker-compose exec bankrot_bot python -m bankrot_bot.run_migrations
```

### Вариант 2: Локально (если установлен alembic)

```bash
# Экспортируйте DATABASE_URL
export DATABASE_URL=postgresql+asyncpg://bankrot:bankrot_password@localhost:5432/bankrot

# Запустите миграции
alembic upgrade head
```

### Вариант 3: Автоматически при старте

Добавьте в Dockerfile или в команду запуска:

```bash
# В docker-compose.yml можно добавить entrypoint:
entrypoint: ["sh", "-c", "python -m bankrot_bot.run_migrations && python bot.py"]
```

## Проверка работы

### 1. Запустите контейнеры:

```bash
docker-compose up -d
```

### 2. Проверьте логи:

```bash
docker-compose logs -f bankrot_bot
```

### 3. Проверьте таблицу в PostgreSQL:

```bash
docker-compose exec postgres psql -U bankrot -d bankrot -c "\d cases"
```

### 4. Тестирование команд:

В Telegram-боте:

1. `/newcase` - создайте новое дело
2. `/mycases` - посмотрите список дел
3. `/case 1` - посмотрите первое дело
4. `/setactive 1` - установите активным
5. `/editcase` - отредактируйте дело

## Логирование и обработка ошибок

Все хендлеры имеют:
- Обработку исключений (try-except)
- Логирование всех операций
- Информативные сообщения об ошибках пользователю

Логи сохраняются в стандартный logger модуля.

## Особенности реализации

1. **FSM Storage**: Используется Redis для хранения состояний FSM и active_case_id
2. **Async/Await**: Все операции асинхронные
3. **Context Manager**: Использование `get_session()` для безопасной работы с БД
4. **Type Hints**: Полная типизация кода
5. **Валидация**: Проверка прав доступа (user_id) на все операции
6. **Форматирование**: Красивый вывод карточек дел с эмодзи

## Переменные окружения

Добавьте в `.env`:

```bash
# PostgreSQL
POSTGRES_DB=bankrot
POSTGRES_USER=bankrot
POSTGRES_PASSWORD=bankrot_password
DATABASE_URL=postgresql+asyncpg://bankrot:bankrot_password@postgres:5432/bankrot

# Redis
REDIS_URL=redis://redis:6379/0
```

## Troubleshooting

### Ошибка подключения к PostgreSQL

Проверьте:
1. Запущен ли контейнер postgres: `docker-compose ps`
2. Правильность DATABASE_URL
3. Здоровье контейнера: `docker-compose logs postgres`

### Ошибка подключения к Redis

Проверьте:
1. Запущен ли контейнер redis: `docker-compose ps`
2. Правильность REDIS_URL

### Миграции не применяются

```bash
# Проверьте версию БД
docker-compose exec bankrot_bot alembic current

# Примените миграции вручную
docker-compose exec bankrot_bot alembic upgrade head
```

## Дальнейшее развитие

Возможные улучшения:
1. Добавить поиск по делам
2. Добавить экспорт дел
3. Добавить массовое редактирование
4. Добавить уведомления по делам
5. Добавить attachment файлов к делам
6. Интеграция с внешними API судов
