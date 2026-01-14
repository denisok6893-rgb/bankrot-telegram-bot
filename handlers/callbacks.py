"""
Callback Handlers - Phase 8, 9, 10, 11
Migrated from bot.py to modular handlers.

Phase 8-9: CASE callbacks (9 handlers) ✅
Phase 10: PROFILE & AI/MISC callbacks (5 handlers) ✅
Phase 11: NAVIGATION & DOCS callbacks (5 handlers) ✅

Total: 19 callbacks migrated (~33% of ~58 total)
"""

# ============================================================================
# CASE CALLBACKS - COMPLETE (9 callbacks total)
# Phase 8-9
# ============================================================================

# Lines 2072-2166 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:edit:") and c.data.count(":") == 2)
async def case_edit_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    case_id = int(call.data.split(":")[-1])

    await state.clear()




    # --- EDIT MENU SHELL (no docs, no CaseCardFill) ---

    row = get_case(uid, case_id)

    if not row:

        await call.message.answer("Дело не найдено.")

        await call.answer()

        return



    try:

        case_number = row[2] if len(row) > 2 else ""

        stage = row[3] if len(row) > 3 else ""

        court = row[5] if len(row) > 5 else ""

        judge = row[6] if len(row) > 6 else ""

        fin_manager = row[7] if len(row) > 7 else ""

        notes = row[8] if len(row) > 8 else ""

    except (IndexError, TypeError) as e:
        logger.warning(f"Failed to parse case row: {e}")
        case_number = stage = court = judge = fin_manager = notes = ""



    text = (

        f"✏️ Редактирование карточки дела #{case_id}\n\n"

        f"Номер дела: {case_number or '—'}\n"

        f"Суд: {court or '—'}\n"

        f"Судья: {judge or '—'}\n"

        f"ФУ: {fin_manager or '—'}\n"

        f"Стадия: {stage or '—'}\n"

        f"Заметки: {notes or '—'}"

    )



    kb = InlineKeyboardBuilder()

    kb.button(text="📋 Показать карточку дела", callback_data=f"case:card:{case_id}")

    kb.button(text="✏️ Номер дела", callback_data=f"case:edit:{case_id}:case_number")

    kb.button(text="✏️ Суд", callback_data=f"case:edit:{case_id}:court")

    kb.button(text="✏️ Судья", callback_data=f"case:edit:{case_id}:judge")

    kb.button(text="✏️ ФУ", callback_data=f"case:edit:{case_id}:fin_manager")

    kb.button(text="✏️ Стадия", callback_data=f"case:edit:{case_id}:stage")

    kb.button(text="🗒 Заметки", callback_data=f"case:edit:{case_id}:notes")

    kb.button(text="🔙 Назад к делу", callback_data=f"case:open:{case_id}")

    kb.adjust(1, 2, 2, 2, 1)



    await call.message.answer(text, reply_markup=kb.as_markup())

    await call.answer()

    return

    # --- /EDIT MENU SHELL ---


    card = get_case_card(uid, case_id) or {}


# Lines 2347-2373 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:file:"))
async def case_file_send(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    parts = call.data.split(":", maxsplit=3)
    if len(parts) < 4:
        await call.answer()
        return

    cid_str, filename = parts[2], parts[3]

    if any(bad in filename for bad in ("/", "\\", "..")):
        await call.message.answer("Некорректное имя файла")
        await call.answer()
        return

    path = GENERATED_DIR / "cases" / cid_str / filename
    if not path.is_file():
        await call.message.answer("Файл не найден...")
        await call.answer()
        return

    await call.message.answer_document(FSInputFile(path))
    await call.answer()


# Lines 2694-2735 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:open:"))
async def case_open(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    row = get_case(uid, cid)
    if not row:
        await call.message.answer("Дело не найдено.")
        await call.answer()
        return

    (cid, _owner_user_id, code_name, case_number, court, judge, fin_manager, stage, notes, created_at, updated_at) = row

    text = (
        f"📌 Дело #{cid}\n"
        f"Код: {code_name}\n"
        f"Номер: {case_number or '-'}\n"
        f"Суд: {court or '-'}\n"
        f"Судья: {judge or '-'}\n"
        f"ФУ: {fin_manager or '-'}\n"
        f"Стадия: {stage or '-'}\n"
        f"Заметки: {notes or '-'}\n"
        f"Создано: {created_at}\n"
        f"Обновлено: {updated_at}"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="📁 Карточка дела", callback_data=f"case:card:{cid}")
    kb.button(text="✏️ Номер дела", callback_data=f"case:edit:{cid}:case_number")
    kb.button(text="✏️ Суд", callback_data=f"case:edit:{cid}:court")
    kb.button(text="✏️ Судья", callback_data=f"case:edit:{cid}:judge")
    kb.button(text="✏️ ФУ", callback_data=f"case:edit:{cid}:fin_manager")
    kb.button(text="✏️ Стадия", callback_data=f"case:edit:{cid}:stage")
    kb.button(text="🗒 Заметки", callback_data=f"case:edit:{cid}:notes")
    kb.button(text="🔙 К списку дел", callback_data="case:list")
    kb.adjust(1, 2, 2, 2)

    await call.message.answer(text, reply_markup=kb.as_markup())
    await call.answer()


# Lines 2738-2773 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_open(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.update_data(card_case_id=cid)
    card = get_case_card(uid, cid) or {}

    lines = [f"📁 Карточка дела #{cid}"]
    for key, title in [
        ("court_name", "Суд"),
        ("court_address", "Адрес суда"),
        ("debtor_full_name", "Должник"),
        ("debtor_gender", "Пол"),
        ("debtor_birth_date", "Дата рождения"),
        ("debtor_address", "Адрес должника"),
        ("passport_series", "Паспорт серия"),
        ("passport_number", "Паспорт номер"),
        ("passport_issued_by", "Кем выдан паспорт"),
        ("passport_date", "Дата выдачи паспорта"),
        ("passport_code", "Код подразделения"),
        ("total_debt_rubles", "Сумма долга (рубли)"),
        ("total_debt_kopeks", "Сумма долга (копейки)"),
    ]:
        lines.append(f"{title}: {card.get(key) or '—'}")

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Заполнить", callback_data=f"card:fill:{cid}")
    kb.button(text="🔙 Назад", callback_data=f"case:open:{cid}")
    kb.adjust(1)

    await call.message.answer("\n".join(lines), reply_markup=kb.as_markup())
    await call.answer()


# Lines 3037-3048 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:card:"))
async def case_card_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.clear()
    await state.update_data(card_case_id=cid)
    await send_card_fill_menu(call.message, uid, cid)
    await call.answer()


# Lines 3050-3085 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:card_edit:"))
async def case_card_edit(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, field = call.data.split(":", maxsplit=3)
    cid = int(cid_str)

    if field not in CASE_CARD_FIELD_META:
        await call.answer()
        return

    row = get_case(uid, cid)
    if not row:
        await call.message.answer("Дело не найдено.")
        await call.answer()
        return

    # ✅ ВАЖНО: creditors — это НЕ текстовое поле, а отдельное меню
    if field == "creditors":
        await state.clear()
        await state.update_data(card_case_id=cid)
        await send_creditors_menu(call.message, uid, cid)
        await call.answer()
        return

    await state.clear()
    await state.update_data(card_cid=cid, card_field=field)
    await state.set_state(CaseCardFill.waiting_value)

    prompt = CASE_CARD_FIELD_META[field]["prompt"] + "\nОтправь '-' чтобы оставить пустым."
    await call.message.answer(prompt)
    await call.answer()


# Lines 3127-3155 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:cardfield:"))
async def card_field_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, field = call.data.split(":", maxsplit=3)
    cid = int(cid_str)

    if field not in CASE_CARD_FIELD_META:
        await call.answer()
        return

    # Кредиторы — отдельное меню, не обычный ввод текста
    if field == "creditors":
        await state.clear()
        await state.update_data(card_case_id=cid)
        await send_creditors_menu(call.message, uid, cid)
        await call.answer()
        return

    await state.clear()
    await state.update_data(card_case_id=cid, card_field_key=field)
    await state.set_state(CaseCardFill.waiting_value)

    prompt = CASE_CARD_FIELD_META[field]["prompt"] + "\nОтправь '-' чтобы оставить пустым."
    await call.message.answer(prompt)
    await call.answer()


# Lines 3312-3324 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:creditors:"))
async def creditors_menu(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    cid = int(call.data.split(":")[2])
    await state.clear()
    await state.update_data(card_case_id=cid)

    await send_creditors_menu(call.message, uid, cid)
    await call.answer()


# Lines 3591-3631 from bot.py
@dp.callback_query(lambda c: c.data.startswith("case:edit:") and c.data.count(":") == 3)
async def case_edit_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    _, _, cid_str, field = call.data.split(":")
    cid = int(cid_str)

    # проверим, что дело существует и твоё
    row = get_case(uid, cid)
    if not row:
        await call.message.answer("Дело не найдено.")
        await call.answer()
        return

    await state.clear()
    await state.update_data(edit_cid=cid, edit_field=field)
    await state.set_state(CaseEdit.value)

    field_titles = {
        "case_number": "номер дела",
        "court": "суд",
        "judge": "судью",
        "fin_manager": "финансового управляющего",
        "stage": "стадию",
        "notes": "заметки",
    }
    title = field_titles.get(field, field)

    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data=f"case:edit:{cid}")
    kb.adjust(1)

    await call.message.answer(
        f"Введи новое значение для «{title}».\nЕсли нужно очистить поле — отправь `-`.",
        reply_markup=kb.as_markup(),
    )

    await call.answer()


# Lines 3632-3682 from bot.py (FSM handler for case_edit_start)
@dp.message(CaseEdit.value)
async def case_edit_apply(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_allowed(uid):
        return

    data = await state.get_data()
    cid = data.get("edit_cid")
    field = data.get("edit_field")

    if not cid or not field:
        await state.clear()
        await message.answer("Что-то пошло не так. Начни заново через карточку дела.")
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пусто. Введи значение или '-' чтобы очистить.")
        return

    value = None if text == "-" else text

    if field in ("case_number", "court", "judge", "fin_manager"):
        update_case_fields(
            uid,
            cid,
            case_number=value if field == "case_number" else None,
            court=value if field == "court" else None,
            judge=value if field == "judge" else None,
            fin_manager=value if field == "fin_manager" else None,
        )
    elif field in ("stage", "notes"):
        update_case_meta(
            uid,
            cid,
            stage=value if field == "stage" else None,
            notes=value if field == "notes" else None,
        )
    else:
        await message.answer("Неизвестное поле для редактирования.")
        await state.clear()
        return
    await state.clear()

    # после сохранения — вернуть в меню редактирования карточки
    fake = type("X", (), {})()
    fake.from_user = message.from_user
    fake.data = f"case:edit:{cid}"
    fake.message = message
    await case_edit_menu(fake, state)


# ============================================================================
# PROFILE CALLBACKS (profile:*)
# Phase 10
# ============================================================================

# Lines 2198-2227 from bot.py
@dp.callback_query(lambda c: c.data == "profile:menu")
async def profile_menu(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    row = get_profile(uid)

    if not row:
        text = "Профиль пока не заполнен.\n\nНажми «✏️ Заполнить профиль»."
    else:
        _, full_name, role, address, phone, email, *_ = row
        text = (
            "👤 Мой профиль:\n"
            f"ФИО/Орг: {full_name or '-'}\n"
            f"Статус: {role or '-'}\n"
            f"Адрес: {address or '-'}\n"
            f"Телефон: {phone or '-'}\n"
            f"Email: {email or '-'}\n\n"
            "Нажми «✏️ Заполнить профиль», чтобы изменить."
        )

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Заполнить профиль", callback_data="profile:edit")
    kb.button(text="🔙 Назад", callback_data="docs:back_menu")
    kb.adjust(1)

    await call.message.answer(text, reply_markup=kb.as_markup())
    await call.answer()


# Lines 2228-2238 from bot.py
@dp.callback_query(lambda c: c.data == "profile:edit")
async def profile_edit_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await state.clear()
    await state.set_state(ProfileFill.full_name)
    await call.message.answer("Введи ФИО или название организации (как будет в документах).")
    await call.answer()


# ============================================================================
# AI & MISC CALLBACKS
# Phase 10
# ============================================================================

# Lines 1552-1560 from bot.py
@dp.callback_query(F.data == "ai:placeholder")
async def ai_placeholder(call: CallbackQuery):
    """Заглушка для ИИ-помощника."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await call.answer("🤖 ИИ-помощник в разработке. Скоро будет доступен!", show_alert=True)


# Lines 1999-2001 from bot.py
@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# Lines 2385-2388 from bot.py
@dp.callback_query(lambda c: c.data == "back:main")
async def back_to_main(call: CallbackQuery):
    await call.message.answer("Главное меню 👇", reply_markup=main_menu_kb())
    await call.answer()


# ============================================================================
# NAVIGATION CALLBACKS (case:list, case:new, back:*)
# Phase 11
# ============================================================================

# Lines 2458-2468 from bot.py
@dp.callback_query(lambda c: c.data == "case:new")
async def case_new(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    await state.clear()
    await state.set_state(CaseCreate.code_name)
    await call.message.answer("Введи кодовое название дела (например: ИВАНОВ_2025).")
    await call.answer()


# Lines 2657-2684 from bot.py
@dp.callback_query(lambda c: c.data == "case:list")
async def case_list(call: CallbackQuery):
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    rows = list_cases(uid)  # берём последние 20 дел
    if not rows:
        await call.message.answer("Пока нет дел. Нажми «➕ Создать дело».")
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    lines = ["📄 Ваши дела (последние 20):"]

    for (cid, code_name, case_number, stage, updated_at) in rows:
        num = case_number or "-"
        st = stage or "-"
        lines.append(f"#{cid} | {code_name} | № {num} | стадия: {st}")
        kb.button(text=f"Открыть #{cid}", callback_data=f"case:open:{cid}")
        kb.button(text="🗂 Заполнить карточку дела", callback_data = f"case:card:{cid}")

    kb.button(text="🔙 Назад", callback_data="back:cases")
    kb.adjust(1)

    await call.message.answer("\n".join(lines), reply_markup=kb.as_markup())
    await call.answer()


# Lines 2686-2692 from bot.py
@dp.callback_query(lambda c: c.data == "back:cases")
async def back_to_cases(call: CallbackQuery):
    await call.message.answer(
        "Раздел «Дела». Выбери действие:",
        reply_markup=cases_menu_ikb()
    )
    await call.answer()


# ============================================================================
# DOCS CALLBACKS (docs:back_menu, docs:choose_case)
# Phase 11
# ============================================================================

# Lines 2376-2380 from bot.py
@dp.callback_query(lambda c: c.data == "docs:back_menu")
async def docs_back_menu(call: CallbackQuery, state: FSMContext):
    cid = await _selected_case_id(state)
    await call.message.answer("Документы: выбери действие 👇", reply_markup=docs_menu_ikb(cid))
    await call.answer()


# Lines 2241-2266 from bot.py
@dp.callback_query(lambda c: c.data == "docs:choose_case")
async def docs_choose_case(call: CallbackQuery):
    """Показывает список дел для выбора дела для документов."""
    uid = call.from_user.id
    if not is_allowed(uid):
        await call.answer()
        return

    rows = list_cases(uid)
    if not rows:
        await call.message.answer("Пока нет дел. Создай дело через «📂 Дела».")
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    lines = ["📄 Выбери дело для генерации документов:"]
    for (cid, code_name, case_number, stage, updated_at) in rows:
        num = case_number or "-"
        lines.append(f"#{cid} | {code_name} | № {num}")
        kb.button(text=f"Дело #{cid}: {code_name}", callback_data=f"docs:case:{cid}")

    kb.button(text="🔙 Назад", callback_data="docs:back_menu")
    kb.adjust(1)

    await call.message.answer("\n".join(lines), reply_markup=kb.as_markup())
    await call.answer()
