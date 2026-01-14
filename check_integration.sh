#!/bin/bash

# Скрипт проверки интеграции модуля "Карточки дел"
# Использование: ./check_integration.sh

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для проверки с выводом статуса
check_step() {
    local step_name="$1"
    local command="$2"

    echo -e "${BLUE}[ПРОВЕРКА]${NC} $step_name"

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}[✓]${NC} $step_name - OK"
        return 0
    else
        echo -e "${RED}[✗]${NC} $step_name - FAILED"
        return 1
    fi
}

# Функция для вывода информации
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Функция для вывода успеха
success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Функция для вывода ошибки
error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Функция для вывода предупреждения
warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

echo "=================================================="
echo "  Проверка интеграции модуля 'Карточки дел'"
echo "=================================================="
echo ""

# 1. Проверка Docker
info "Шаг 1: Проверка Docker"
if ! command -v docker &> /dev/null; then
    error "Docker не установлен"
    exit 1
fi

if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif docker-compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    error "Docker Compose не установлен"
    exit 1
fi

success "Docker установлен"
docker --version
$COMPOSE_CMD version
echo ""

# 2. Проверка файла .env
info "Шаг 2: Проверка конфигурации"
if [ ! -f .env ]; then
    error "Файл .env не найден"
    exit 1
fi

if grep -q "your_telegram_bot_token" .env; then
    warning "BOT_TOKEN не настроен в .env"
    warning "Отредактируйте .env и добавьте ваш токен от @BotFather"
fi

success "Файл .env найден"
echo ""

# 3. Проверка статуса контейнеров
info "Шаг 3: Проверка статуса Docker контейнеров"
if ! $COMPOSE_CMD ps | grep -q "bankrot_postgres"; then
    warning "Контейнеры не запущены. Запускаю..."
    $COMPOSE_CMD up -d
    sleep 10
fi

echo ""
$COMPOSE_CMD ps
echo ""

# 4. Проверка health check PostgreSQL
info "Шаг 4: Проверка PostgreSQL"
POSTGRES_STATUS=$($COMPOSE_CMD ps postgres | grep -o "healthy" || echo "not healthy")
if [ "$POSTGRES_STATUS" == "healthy" ]; then
    success "PostgreSQL работает (healthy)"
else
    error "PostgreSQL не готов: $POSTGRES_STATUS"
fi

# Проверка подключения к БД
if $COMPOSE_CMD exec -T postgres psql -U bankrot -d bankrot -c "\conninfo" &> /dev/null; then
    success "Подключение к PostgreSQL установлено"
else
    error "Не удалось подключиться к PostgreSQL"
fi
echo ""

# 5. Проверка Redis
info "Шаг 5: Проверка Redis"
REDIS_STATUS=$($COMPOSE_CMD ps redis | grep -o "healthy" || echo "not healthy")
if [ "$REDIS_STATUS" == "healthy" ]; then
    success "Redis работает (healthy)"
else
    error "Redis не готов: $REDIS_STATUS"
fi

# Проверка подключения к Redis
if $COMPOSE_CMD exec -T redis redis-cli ping | grep -q "PONG"; then
    success "Redis отвечает на ping"
else
    error "Redis не отвечает"
fi
echo ""

# 6. Проверка таблицы cases
info "Шаг 6: Проверка таблицы cases"
if $COMPOSE_CMD exec -T postgres psql -U bankrot -d bankrot -c "\d cases" &> /dev/null; then
    success "Таблица cases создана"

    # Показываем структуру таблицы
    echo ""
    info "Структура таблицы cases:"
    $COMPOSE_CMD exec -T postgres psql -U bankrot -d bankrot -c "\d cases"
    echo ""

    # Показываем количество записей
    CASES_COUNT=$($COMPOSE_CMD exec -T postgres psql -U bankrot -d bankrot -t -c "SELECT COUNT(*) FROM cases;" | tr -d ' ')
    info "Записей в таблице cases: $CASES_COUNT"
else
    warning "Таблица cases не найдена"
    info "Попытка запустить миграции..."

    if $COMPOSE_CMD exec -T bankrot_bot python -m bankrot_bot.run_migrations; then
        success "Миграции выполнены"
    else
        error "Не удалось выполнить миграции"
    fi
fi
echo ""

# 7. Проверка логов бота
info "Шаг 7: Проверка логов бота"
if $COMPOSE_CMD logs bankrot_bot | grep -q "PostgreSQL database initialized"; then
    success "PostgreSQL инициализирован в боте"
else
    warning "Инициализация PostgreSQL не найдена в логах"
fi

if $COMPOSE_CMD logs bankrot_bot | grep -q "Bot starting"; then
    success "Бот запущен"
else
    warning "Сообщение о запуске бота не найдено"
fi

# Проверка на ошибки
ERROR_COUNT=$($COMPOSE_CMD logs bankrot_bot | grep -ci "error" || echo 0)
if [ "$ERROR_COUNT" -gt 0 ]; then
    warning "Найдено $ERROR_COUNT упоминаний 'error' в логах"
    info "Последние ошибки:"
    $COMPOSE_CMD logs --tail=20 bankrot_bot | grep -i error || echo "Нет критических ошибок"
else
    success "Ошибок в логах не найдено"
fi
echo ""

# 8. Проверка веб-сервиса
info "Шаг 8: Проверка веб-сервиса (healthz)"
if curl -s http://localhost:8101/healthz | grep -q "ok"; then
    success "Healthz endpoint отвечает"
else
    warning "Healthz endpoint не доступен (возможно, webhook не используется)"
fi
echo ""

# 9. Проверка кода интеграции
info "Шаг 9: Проверка кода интеграции"

if grep -q "RedisStorage" bot.py; then
    success "RedisStorage найден в bot.py"
else
    error "RedisStorage не найден в bot.py"
fi

if grep -q "from bankrot_bot.handlers import cases as cases_handlers" bot.py; then
    success "Импорт cases_handlers найден"
else
    error "Импорт cases_handlers не найден"
fi

if grep -q "dp.include_router(cases_handlers.router)" bot.py; then
    success "Роутер cases_handlers зарегистрирован"
else
    error "Роутер cases_handlers не зарегистрирован"
fi

if grep -q "await init_pg_db()" bot.py; then
    success "Инициализация PostgreSQL добавлена"
else
    error "Инициализация PostgreSQL не найдена"
fi
echo ""

# 10. Сводка
echo "=================================================="
echo "              СВОДКА ПРОВЕРКИ"
echo "=================================================="
echo ""

# Подсчет успешных проверок
CHECKS_PASSED=0
CHECKS_TOTAL=10

if command -v docker &> /dev/null; then ((CHECKS_PASSED++)); fi
if [ -f .env ]; then ((CHECKS_PASSED++)); fi
if [ "$POSTGRES_STATUS" == "healthy" ]; then ((CHECKS_PASSED++)); fi
if [ "$REDIS_STATUS" == "healthy" ]; then ((CHECKS_PASSED++)); fi
if $COMPOSE_CMD exec -T postgres psql -U bankrot -d bankrot -c "\d cases" &> /dev/null; then ((CHECKS_PASSED++)); fi
if $COMPOSE_CMD logs bankrot_bot | grep -q "PostgreSQL database initialized"; then ((CHECKS_PASSED++)); fi
if grep -q "RedisStorage" bot.py; then ((CHECKS_PASSED++)); fi
if grep -q "cases_handlers" bot.py; then ((CHECKS_PASSED++)); fi
if grep -q "dp.include_router" bot.py; then ((CHECKS_PASSED++)); fi
if grep -q "await init_pg_db()" bot.py; then ((CHECKS_PASSED++)); fi

echo "Пройдено проверок: $CHECKS_PASSED из $CHECKS_TOTAL"
echo ""

if [ $CHECKS_PASSED -eq $CHECKS_TOTAL ]; then
    success "ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!"
    echo ""
    info "Следующие шаги:"
    echo "  1. Откройте бота в Telegram"
    echo "  2. Отправьте команду /start"
    echo "  3. Попробуйте создать дело: /newcase"
    echo "  4. Проверьте список дел: /mycases"
    echo ""
    success "Интеграция завершена успешно!"
elif [ $CHECKS_PASSED -ge 7 ]; then
    warning "Большинство проверок пройдено ($CHECKS_PASSED/$CHECKS_TOTAL)"
    info "Проверьте предупреждения выше и исправьте проблемы"
else
    error "Обнаружены проблемы ($CHECKS_PASSED/$CHECKS_TOTAL проверок пройдено)"
    info "Исправьте ошибки выше и запустите скрипт снова"
    exit 1
fi

echo "=================================================="
echo ""

# Предложение просмотра логов
read -p "Показать последние 30 строк логов бота? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    info "Последние логи бота:"
    echo "=================================================="
    $COMPOSE_CMD logs --tail=30 bankrot_bot
    echo "=================================================="
fi

echo ""
info "Для полного просмотра логов используйте:"
echo "  $COMPOSE_CMD logs -f bankrot_bot"
echo ""
info "Для остановки: $COMPOSE_CMD stop"
info "Для перезапуска: $COMPOSE_CMD restart bankrot_bot"
echo ""
