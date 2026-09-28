"""Чтение карточки заявки Apex в JSON.

Портал старый, вёрстка табличная: слева ячейка с подписью, справа поле ввода.
Поэтому значения ищутся по тексту подписи, а не по id элементов — id в GWT
генерируются при сборке и меняются после каждого обновления портала.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import Page

import portal

# Подписи полей взяты с экрана карточки заявки.
FIELDS = {
    "make": "Марка а/м:",
    "model": "Модель а/м:",
    "year": "Год выпуска:",
    "color": "Цвет:",
    "engine_no": "№ двигателя:",
    "sts": "СТС:",
    "pts": "ПТС:",
    "owner": "Владелец:",
    "owner_address": "Адрес владельца:",
    "owner_phone": "Телефон владельца:",
    "odometer": "Пробег, км:",
    "accident_date": "Дата ДТП/СС:",
    "region": "Экономический регион:",
    "policy_number": "№ полиса:",
    "claim_number": "№ убытка:",
    "task_code": "Код задачи:",
    "accident_place": "Место аварии:",
    "comment": "Комментарий:",
    "extra_actions": "Доп. действия:",
    "inspection_object": "Объект осмотра:",
    "inspection_purpose": "Цель осмотра:",
    "inspection_type": "Тип осмотра:",
    "at_fault": "Виновен в ДТП:",
    "franchise": "Франшиза:",
    "liability_limit": "Лимит ответственности:",
    "service_station": "СТО:",
    "amount": "Сумма, руб.:",
}

# Регион задаёт ставки. Место аварии пишут сокращённо.
CITY_ALIASES = {
    "СПБ": "Санкт-Петербург",
    "СПб": "Санкт-Петербург",
    "МСК": "Москва",
    "НСК": "Новосибирск",
    "КЗН": "Казань",
}

CLAIM_TYPES = ["ПВУ", "ОСАГО", "КАСКО"]

_VALUE_JS = """
(label) => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').replace(/\\*/g, '').trim();
  const target = norm(label);
  for (const cell of document.querySelectorAll('td, th, label, div')) {
    if (norm(cell.textContent) !== target) continue;
    const row = cell.closest('tr');
    // Значение лежит в соседней ячейке той же строки.
    const scope = cell.nextElementSibling || row || cell.parentElement;
    if (!scope) continue;

    // Радиокнопки: нужен текст выбранного варианта, а не первого попавшегося.
    const radios = scope.querySelectorAll('input[type=radio]');
    if (radios.length) {
      for (const r of radios) {
        if (!r.checked) continue;
        const own = r.labels && r.labels.length ? r.labels[0].textContent : '';
        const next = r.nextSibling ? r.nextSibling.textContent : '';
        return norm(own || next) || 'да';
      }
      return '';
    }

    const field = scope.querySelector('input, textarea, select')
               || (row || document).querySelector('input, textarea, select');
    if (!field) continue;
    if (field.tagName === 'SELECT') {
      const opt = field.options[field.selectedIndex];
      return opt ? opt.textContent.trim() : '';
    }
    if (field.type === 'checkbox') return field.checked ? 'да' : 'нет';
    return (field.value || '').trim();
  }
  return null;
}
"""


def read_field(page: Page, label: str) -> str | None:
    return page.evaluate(_VALUE_JS, label)


def detect_claim_type(page: Page) -> str | None:
    """Тип заявки: ПВУ / ОСАГО / КАСКО.

    Сначала пробуем по № убытка — в записи он был `Z692/PVU/13580/26`,
    затем по видимому тексту страницы.
    """
    claim_no = read_field(page, FIELDS["claim_number"]) or ""
    if "/PVU/" in claim_no.upper():
        return "ПВУ"
    body = page.locator("body").inner_text()
    for t in CLAIM_TYPES:
        if re.search(rf"\b{t}\b", body):
            return t
    return None


def parse_comments(raw: str) -> list[dict]:
    """Комментарии приходят строками вида `29-01-2026 11:19:Фамилия И.О.:текст`."""
    out = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(\d{2}[-.]\d{2}[-.]\d{4}\s+\d{2}:\d{2})\s*:\s*(.+?)\s*:\s*(.*)$", line)
        out.append(
            {"at": m.group(1), "author": m.group(2), "text": m.group(3)}
            if m else {"at": "", "author": "", "text": line}
        )
    return out


def expand_city(place: str) -> str:
    """СПБ -> Санкт-Петербург, для остального возвращает как есть."""
    for short, full in CITY_ALIASES.items():
        if re.search(rf"\b{short}\b", place or "", re.IGNORECASE):
            return re.sub(rf"\b{short}\b", full, place, flags=re.IGNORECASE)
    return place or ""


def read_claim(page: Page, request_id: str) -> dict:
    """Собирает карточку заявки в словарь."""
    data: dict = {"request_id": request_id, "url": page.url, "fields": {}, "missing": []}
    for key, label in FIELDS.items():
        value = read_field(page, label)
        if value is None:
            data["missing"].append(label)
        else:
            data["fields"][key] = value

    data["claim_type"] = detect_claim_type(page)
    data["comments"] = parse_comments(data["fields"].get("comment", ""))
    data["accident_place_full"] = expand_city(data["fields"].get("accident_place", ""))
    return data


def fetch(session: portal.Session, request_id: str) -> dict:
    page = session.page
    page.goto(portal.REQUEST_URL.format(id=request_id), wait_until="networkidle")
    return read_claim(page, request_id)


def save(claim: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{claim['request_id']}.json"
    path.write_text(json.dumps(claim, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
