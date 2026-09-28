"""Распознавание акта осмотра: PDF -> JSON через vision-модель Claude."""
from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic

import pages as pages_mod
import schema

MODEL_CLASSIFY = os.environ.get("ACT_MODEL_CLASSIFY", "claude-sonnet-5")
MODEL_EXTRACT = os.environ.get("ACT_MODEL_EXTRACT", "claude-opus-5")

CLASSIFY_PROMPT = """Ты обрабатываешь скан пакета документов по страховому случаю (Россия, ОСАГО/КАСКО/ПВУ).
Определи, что за страница перед тобой, и нужен ли поворот, чтобы текст читался.

act_damages — только лист с таблицей повреждённых деталей (колонки Замена/Ремонт/Окраска
или Окраска/Замена/Ремонт н/ч). act_header — лист с VIN, госномером, комплектацией,
дефектами эксплуатации. Страница может быть сфотографирована под углом или вверх ногами."""

VEHICLE_PROMPT = """Извлеки данные с листа 1 акта осмотра ТС.
Часть полей вписана от руки, часть отмечена галочками или обведена кружком.
Если поле неразборчиво — не угадывай, впиши его имя в unreadable_fields.
Даты приводи к ДД.ММ.ГГГГ. VIN — 17 символов, латиница и цифры, читай посимвольно по клеткам."""

DAMAGES_PROMPT = """Извлеки таблицу повреждённых деталей.

Встречаются три бланка:
1. Акт осмотра НМЦ «ТехЮр Сервис»: № | Наименование детали | Характеристика повреждения |
   Длина,см | Ширина,см | Замена | Ремонт | Окраска.
2. «Заключение к Акту осмотра»: № | Наименование детали (узла, элемента) | сторона |
   Предварительный способ восстановления: Окраска | Замена | Ремонт, н/ч.
   Внимание: порядок колонок здесь другой, не путай Окраску с Заменой.
3. Таблица без колонок способа восстановления: деталь | сторона | вид, размер повреждения.

Правила:
- Одна строка таблицы = один элемент items. Пустые строки пропускай.
- Сначала определи бланк и запиши его в form_template, потом читай колонки по шапке
  этого бланка, а не по позиции слева направо.
- Галочка, крестик или любая пометка в клетке = true. Пустая клетка и прочерк (—) = false.
  В бланке 2 в колонке «Ремонт, н/ч» вместо галочки может стоять число нормо-часов —
  тогда repair = true, а число в norm_hours.
- Пометка стоит между колонками или неоднозначна — confidence "low".
- side: колонка «сторона», обычно рукописное L или R. Пусто — оставь "".
- part пиши дословно, включая сокращения (пер., зад., лев., прав., РМ, ТДМ, ЧЗАМ, ДЕФ).
  Не расшифровывай и не нормализуй — это делает следующий этап.
- Если почерк неразборчив — confidence "low", а в part пиши то, что видно, со знаком "?".
- Ничего не выдумывай. Лучше low confidence, чем правдоподобная выдумка."""


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "Не задан ANTHROPIC_API_KEY. Возьми ключ на console.anthropic.com "
            "и выполни: export ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic()


def _call(client, model: str, prompt: str, page: pages_mod.Page, tool: dict) -> dict:
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": page.b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError(f"Модель не вызвала инструмент {tool['name']}")


def classify(client, page: pages_mod.Page) -> dict:
    return _call(client, MODEL_CLASSIFY, CLASSIFY_PROMPT, page, schema.CLASSIFY_TOOL)


def recognize_pdf(pdf_path: Path, dpi: int = 200, limit: int | None = None) -> dict:
    """Полный проход: классификация всех страниц, затем извлечение с нужных."""
    client = _client()
    rendered = pages_mod.render(pdf_path, dpi=dpi)
    if limit:
        rendered = rendered[:limit]

    result: dict = {
        "source": str(pdf_path),
        "page_map": [],
        "vehicle": None,
        "damages": [],
        "undamaged_parts": [],
        "needs_manual": [],
    }

    for page in rendered:
        info = classify(client, page)
        page = pages_mod.rotate(page, info.get("rotation_needed", 0))
        result["page_map"].append({"page": page.index + 1, **info})

        if info["kind"] == "act_header" and result["vehicle"] is None:
            result["vehicle"] = _call(client, MODEL_EXTRACT, VEHICLE_PROMPT, page, schema.VEHICLE_TOOL)
        elif info["kind"] == "act_damages" and info.get("has_filled_rows", True):
            data = _call(client, MODEL_EXTRACT, DAMAGES_PROMPT, page, schema.DAMAGES_TOOL)
            for item in data.get("items", []):
                item["page"] = page.index + 1
                result["damages"].append(item)
                if item.get("confidence") == "low":
                    result["needs_manual"].append(
                        f"стр.{page.index + 1} поз.{item.get('n')}: {item.get('part')}"
                    )
            result["undamaged_parts"] += data.get("undamaged_parts", [])

    if result["vehicle"] and result["vehicle"].get("unreadable_fields"):
        result["needs_manual"] += [
            f"лист 1, поле: {f}" for f in result["vehicle"]["unreadable_fields"]
        ]
    return result


def save(result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = Path(result["source"]).stem.replace(" ", "_") + ".json"
    path = out_dir / name
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
