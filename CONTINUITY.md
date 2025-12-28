# CONTINUITY.md

## Goal (достигнута)

Получить один корректно заполненный DOCX:  
**«Заявление о банкротстве»**, без `{{...}}`,  
с динамическими кредиторами и дефолтами для отсутствующих данных.

Результат подтверждён: документ генерируется стабильно, плейсхолдеров нет,
юридические формулировки корректны.

---

## Scope (строго соблюдён)

Менялась **только** функция:

- `build_bankruptcy_petition_doc(case_row, card)`

Не затрагивались:
- импорты
- меню
- FSM / хендлеры
- миграции БД
- другие функции

---

## Current State (зафиксировано)

- Ветка: `petition-v1`
- `bot.py` компилируется (`python -m py_compile bot.py` — OK)
- Генерация DOCX стабильна через работающий systemd-сервис `bankrot-bot`
- Документ сохраняется в:

/root/bankrot_bot/generated/cases/<cid>/

---

## Template placeholders (23 / 23 закрыты)

Все плейсхолдеры шаблона гарантированно заменяются:

- attachments_list  
- certificate_date  
- certificate_number  
- court_address  
- court_name  
- creditors_block  
- date  
- debtor_address  
- debtor_birth_date  
- debtor_full_name  
- debtor_inn  
- debtor_passport_code  
- debtor_passport_date  
- debtor_passport_issued_by  
- debtor_passport  
- debtor_phone  
- debtor_snils  
- deposit_deferral_request  
- financial_manager_info  
- marital_status  
- total_debt_kopeks  
- total_debt_rubles  
- vehicle_block  

---

## Defaults (утверждены и реализованы)

- Текстовые поля → `"не указано"`
- `total_debt_rubles` → `"0"`
- `total_debt_kopeks` → `"00"`
- `deposit_deferral_request` → `""`
- `attachments_list` → `""`
- `vehicle_block` → `"Транспортные средства: отсутствуют."`
- `creditors_block` → нейтральный текст, если нет данных

---

## Creditors logic (реализовано)

Приоритет:
1. `card["creditors_text"]` — если есть
2. `build_creditors_block(card["creditors"])` — если список
3. Нейтральный текст — если данных нет

---

## Marital status (нормализация завершена)

Поддерживается отображение кодов в юридический текст:

- `married`  → `Состоит в зарегистрированном браке.`
- `single`   → `В браке не состоит.`
- `divorced` → `Брак расторгнут.`
- `widowed`  → `Вдовец/вдова.`

Если в карточке уже хранится русский текст — используется как есть.  
Если поле пустое — `"не указано"`.

---

## Word / python-docx workaround (важно)

Для надёжности реализованы **два прохода подстановки**:

1. `_replace_placeholders_strong(doc, mapping)`
2. Добор по `run.text` — для случаев, когда Word разрывает `{{...}}` между runs

Это гарантирует отсутствие плейсхолдеров в итоговом DOCX.

---

## What failed earlier (зафиксировано)

- Использование Codex приводило к:
- переписыванию импорта/верх файла
- добавлению несуществующих зависимостей
- конфликтам patch’ей
- Причина проблем с `{{...}}` — разрыв плейсхолдеров Word’ом по runs

---

## Decisions (приняты и подтверждены)

- Отказ от Codex для этого участка
- Ручная правка строго в рамках одной функции
- Проверка результата только по фактическому DOCX
- Сервисный перезапуск через systemd (`bankrot-bot`)

---

## Status

✅ Цель достигнута  
✅ Реализация стабильна  
✅ Изменения зафиксированы в Git  

Последний коммит:

Fix bankruptcy petition placeholders and normalize marital status text

---

## Next (опционально)

- Нормализация других полей карточки (пол, дети, занятость)
- Валидация карточки дела перед генерацией
- Добавление автопроверки DOCX на `{{...}}`
- Переход к следующему документу

## 28.12.2025 — Заявление о банкротстве (petition) доведено до образца юриста

Сделано:
- Привели шаблон templates/petitions/bankruptcy_petition.docx к виду как у подаваемого заявления:
  - исправлена опечатка "со со ст." -> "со ст."
  - СРО/финуправляющий оформлены через {{financial_manager_info}} (отдельный {{sro_name}} не нужен)
- Исправили пунктуацию в ip_status_text (убрали двойные точки)
- Нормализовали шапку кредиторов: в шапке только список, в тексте суммы
- Стабилизировали меню документов: case_docs не падает на fake.answer (проверка hasattr)

Проверка:
- python -m py_compile bot.py
- systemctl restart bankrot-bot
- генерация заявления по делу проходит без {{...}} плейсхолдеров

Дальше (план):
1) Привести attachments_list к реальному списку приложений (если надо)
2) Доделать мастер кредиторов (обязательства: руб/коп/источник) и валидацию
3) Добавить удобное поле/шаг в карточке дела для financial_manager_info (СРО) и подсказку формата
