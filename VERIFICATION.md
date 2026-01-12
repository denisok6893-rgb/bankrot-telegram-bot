# Команды проверки интеграции модуля "Карточки дел"

## Что было интегрировано

### ✅ Изменения в bot.py

1. **RedisStorage для FSM** (строка 1270-1275)
   - Заменен `MemoryStorage` на `RedisStorage`
   - Подключение к Redis через переменную окружения `REDIS_URL`

2. **Импорты** (строки 37-38)
   - `from bankrot_bot.database import init_db as init_pg_db`
   - `from bankrot_bot.handlers import cases as cases_handlers`

3. **Регистрация роутера** (строка 1278)
   - `dp.include_router(cases_handlers.router)`

4. **Инициализация PostgreSQL** (строки 3585-3586)
   - Добавлен вызов `await init_pg_db()`
   - Сохранена инициализация старой SQLite БД для совместимости

### ✅ Готовые компоненты

- `bankrot_bot/database.py` - настройка async PostgreSQL
- `bankrot_bot/handlers/cases.py` - CRUD хендлеры
- `bankrot_bot/models/case.py` - модель Case
- `alembic/versions/20260112_0000_001_create_cases_table.py` - миграция
- `docker-compose.yml` - Redis и PostgreSQL сервисы
- `requirements.txt` - все зависимости

---

## 1. Проверка Docker-окружения

### Запустить контейнеры

```bash
docker-compose up -d
```

### Проверить статус всех сервисов

```bash
docker-compose ps
```

Должны быть запущены:
- `bankrot_postgres` (healthy)
- `bankrot_redis` (healthy)
- `bankrot_bot` (running)
- `bankrot_web` (running)

### Проверить логи бота

```bash
docker-compose logs -f bankrot_bot
```

Ожидаемые сообщения:
- `PostgreSQL database initialized`
- `Database tables created successfully`
- `Bot starting in POLLING/WEBHOOK mode`

---

## 2. Проверка базы данных

### Проверить подключение к PostgreSQL

```bash
docker-compose exec postgres psql -U bankrot -d bankrot -c "\conninfo"
```

### Проверить таблицу cases

```bash
docker-compose exec postgres psql -U bankrot -d bankrot -c "\d cases"
```

Ожидаемая структура:
- `id` (integer, PK)
- `user_id` (bigint)
- `debtor_name` (varchar)
- `debtor_inn` (varchar)
- `case_number` (varchar)
- `court` (varchar)
- `stage` (varchar)
- `manager_name` (varchar)
- `created_at` (timestamp with time zone)
- `updated_at` (timestamp with time zone)

### Проверить индексы

```bash
docker-compose exec postgres psql -U bankrot -d bankrot -c "\d+ cases"
```

Должен быть индекс: `ix_cases_user_id`

---

## 3. Проверка Redis

### Проверить подключение к Redis

```bash
docker-compose exec redis redis-cli ping
```

Ожидаемый ответ: `PONG`

### Проверить FSM данные (после использования бота)

```bash
docker-compose exec redis redis-cli KEYS "*"
```

---

## 4. Проверка миграций Alembic

### Проверить текущую версию БД

```bash
docker-compose exec bankrot_bot alembic current
```

Ожидаемый вывод: `001 (head)`

### Проверить историю миграций

```bash
docker-compose exec bankrot_bot alembic history
```

### Применить миграции вручную (если нужно)

```bash
docker-compose exec bankrot_bot python -m bankrot_bot.run_migrations
```

ИЛИ

```bash
docker-compose exec bankrot_bot alembic upgrade head
```

---

## 5. Функциональное тестирование в Telegram

### Команды для тестирования:

1. **Создать новое дело**
   ```
   /newcase
   ```
   Заполните все поля пошагово

2. **Посмотреть список дел**
   ```
   /mycases
   ```
   Должны отобразиться созданные дела

3. **Просмотр карточки дела**
   ```
   /case 1
   ```
   Должна отобразиться карточка с полной информацией

4. **Установить активное дело**
   ```
   /setactive 1
   ```

5. **Редактировать активное дело**
   ```
   /editcase
   ```

6. **Отменить операцию**
   ```
   /cancel
   ```

### Проверка данных в БД после создания дела

```bash
docker-compose exec postgres psql -U bankrot -d bankrot -c "SELECT id, user_id, debtor_name, case_number FROM cases;"
```

---

## 6. Проверка совместимости со старым функционалом

### Webhook (если используется)

```bash
# Проверить healthz endpoint
curl http://localhost:8101/healthz
```

Ожидаемый ответ: `{"status":"ok"}`

### Существующие команды

Убедитесь, что работают:
- `/start` - главное меню
- Генерация документов
- Профиль пользователя
- Другие существующие функции

---

## 7. Проверка логов на ошибки

### Логи бота

```bash
docker-compose logs bankrot_bot | grep -i error
docker-compose logs bankrot_bot | grep -i exception
```

Не должно быть критических ошибок

### Логи PostgreSQL

```bash
docker-compose logs postgres | grep -i error
```

### Логи Redis

```bash
docker-compose logs redis | grep -i error
```

---

## 8. Мониторинг производительности

### Проверить количество подключений к PostgreSQL

```bash
docker-compose exec postgres psql -U bankrot -d bankrot -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'bankrot';"
```

### Проверить размер базы данных

```bash
docker-compose exec postgres psql -U bankrot -d bankrot -c "SELECT pg_size_pretty(pg_database_size('bankrot'));"
```

### Проверить использование Redis

```bash
docker-compose exec redis redis-cli INFO memory
```

---

## 9. Troubleshooting

### Если бот не запускается

1. Проверить переменные окружения:
   ```bash
   docker-compose exec bankrot_bot env | grep -E "DATABASE_URL|REDIS_URL"
   ```

2. Проверить здоровье сервисов:
   ```bash
   docker-compose ps
   ```

3. Проверить подключение к PostgreSQL из контейнера бота:
   ```bash
   docker-compose exec bankrot_bot python -c "import asyncio; from bankrot_bot.database import engine; asyncio.run(engine.connect())"
   ```

### Если не работают команды модуля cases

1. Проверить, что роутер зарегистрирован:
   ```bash
   docker-compose logs bankrot_bot | grep "cases_handlers"
   ```

2. Проверить FSM storage:
   ```bash
   docker-compose exec redis redis-cli KEYS "fsm:*"
   ```

### Если таблица cases не создалась

1. Запустить миграции вручную:
   ```bash
   docker-compose exec bankrot_bot python -m bankrot_bot.run_migrations
   ```

2. Проверить логи миграции:
   ```bash
   docker-compose logs bankrot_bot | grep -i "migration\|alembic"
   ```

---

## 10. Остановка и очистка

### Остановить контейнеры

```bash
docker-compose down
```

### Остановить и удалить volumes (ВНИМАНИЕ: удалит все данные)

```bash
docker-compose down -v
```

### Пересобрать и перезапустить

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## Контрольный список интеграции

- [x] bot.py обновлен (RedisStorage, импорты, роутер, init_db)
- [x] docker-compose.yml содержит postgres и redis
- [x] requirements.txt содержит все зависимости
- [x] Миграция Alembic создана
- [x] database.py настроен
- [x] handlers/cases.py реализован
- [x] models/case.py создан
- [ ] Контейнеры запущены и здоровы
- [ ] Миграции применены
- [ ] Команды /newcase, /mycases, /case работают
- [ ] Старый функционал не нарушен
- [ ] Нет ошибок в логах

---

## Полезные ссылки

- [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md) - подробное руководство по интеграции
- [README.md](./README.md) - основная документация проекта
- [alembic/versions/](./alembic/versions/) - миграции базы данных
