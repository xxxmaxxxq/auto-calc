"""JSON-схемы результата распознавания акта осмотра."""

PAGE_KINDS = [
    "act_header",     # лист 1 акта: данные ТС, собственник, дефекты эксплуатации
    "act_damages",    # таблица позиций: деталь / замена / ремонт / окраска / н/ч
    "act_other",      # прочие листы акта (особое мнение, приложения)
    "pts",            # ПТС
    "sts",            # СТС
    "photo",          # фотография повреждений
    "order",          # заказ-наряд / калькуляция СТОА
    "unknown",
]

CLASSIFY_TOOL = {
    "name": "classify_page",
    "description": "Определить тип страницы документа и её ориентацию.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": PAGE_KINDS},
            "rotation_needed": {
                "type": "integer",
                "enum": [0, 90, 180, 270],
                "description": "На сколько градусов по часовой стрелке повернуть, чтобы текст читался нормально.",
            },
            "has_filled_rows": {
                "type": "boolean",
                "description": "Только для act_damages: есть ли хоть одна заполненная строка позиций.",
            },
            "confidence": {"type": "number"},
        },
        "required": ["kind", "rotation_needed", "confidence"],
    },
}

VEHICLE_TOOL = {
    "name": "extract_vehicle",
    "description": "Извлечь данные ТС и осмотра с листа 1 акта осмотра.",
    "input_schema": {
        "type": "object",
        "properties": {
            "act_number": {"type": "string"},
            "policy_number": {"type": "string"},
            "claim_type": {"type": "string", "description": "ПВУ / ОСАГО / КАСКО, как отмечено в акте"},
            "insurer": {"type": "string"},
            "inspection_date": {"type": "string", "description": "ДД.ММ.ГГГГ ЧЧ:ММ"},
            "inspection_place": {"type": "string"},
            "accident_date": {"type": "string"},
            "accident_place": {"type": "string"},
            "plate": {"type": "string"},
            "vin": {"type": "string"},
            "make_model": {"type": "string"},
            "year": {"type": "string"},
            "odometer": {"type": "string"},
            "color": {"type": "string"},
            "owner": {"type": "string"},
            "pre_existing_defects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Дефекты эксплуатации и следы ранее проведённого ремонта, дословно.",
            },
            "expert": {"type": "string"},
            "notes": {"type": "string", "description": "Всё, что не влезло в поля, но важно для расчёта."},
            "unreadable_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Поля, которые не удалось прочитать уверенно. Не угадывать — перечислять здесь.",
            },
        },
        "required": ["plate", "make_model", "unreadable_fields"],
    },
}

DAMAGES_TOOL = {
    "name": "extract_damages",
    "description": "Извлечь таблицу повреждённых деталей с листа акта осмотра.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer", "description": "Номер строки в таблице"},
                        "part": {"type": "string", "description": "Наименование детали как написано в акте"},
                        "damage": {"type": "string", "description": "Характеристика повреждения / вид, размер повреждения"},
                        "side": {
                            "type": "string",
                            "enum": ["L", "R", ""],
                            "description": "Колонка 'сторона': L (лев.), R (прав.) или пусто.",
                        },
                        "length_cm": {"type": "string"},
                        "width_cm": {"type": "string"},
                        "replace": {"type": "boolean", "description": "Отмечена колонка Замена"},
                        "repair": {"type": "boolean", "description": "Отмечена колонка Ремонт"},
                        "paint": {"type": "boolean", "description": "Отмечена колонка Окраска"},
                        "norm_hours": {"type": "string", "description": "Нормо-часы, если проставлены"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "low = почерк неразборчив, нужен ручной ввод",
                        },
                    },
                    "required": ["n", "part", "confidence"],
                },
            },
            "undamaged_parts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Подчёркнутые детали из строки 'Детали не имеющие повреждений'.",
            },
            "form_template": {
                "type": "string",
                "enum": ["zamena_remont_okraska", "okraska_zamena_remont_nch", "no_marks", "other"],
                "description": (
                    "zamena_remont_okraska — бланк акта осмотра НМЦ ТехЮр Сервис. "
                    "okraska_zamena_remont_nch — 'Заключение к Акту осмотра', колонки Окраска/Замена/Ремонт н/ч. "
                    "no_marks — таблица без колонок способа восстановления, только деталь и повреждение."
                ),
            },
            "page_note": {"type": "string"},
        },
        "required": ["items", "form_template"],
    },
}
