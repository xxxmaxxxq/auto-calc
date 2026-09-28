"""Блок A: работа с порталом Apex/Uzon. Только чтение и скачивание.

Логин делается руками один раз: браузер запускается с постоянным профилем в
`~/.auto-calc/profile`, и сессия переживает перезапуски. Пароли в коде не
хранятся и скриптом не вводятся.
"""
from __future__ import annotations

import os
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

PROFILE_DIR = Path.home() / ".auto-calc" / "chrome-profile"
CDP_URL = "http://localhost:9222"
BASE = os.environ.get("PORTAL_BASE_URL", "https://portal.example.com")
REQUEST_URL = BASE + "/apex/requestedit.htm?id={id}"
CALC_URL = BASE + "/uzon/#requestWorkCalc;request={id}"

# Класс из регламента. GWT генерирует его при сборке, поэтому он меняется после
# каждого обновления портала и используется только как запасной вариант.
LEGACY_CALC_CLASS = "DABET2D-u-r"


@dataclass
class Session:
    page: Page
    _ctx: object = None
    _pw: object = None

    def close(self) -> None:
        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()


def open_session(headless: bool = False, downloads: Path | None = None,
                 attach: bool = False) -> Session:
    """Открывает настоящий Google Chrome с отдельным профилем auto-calc.

    attach=True — не запускать браузер, а подключиться к уже открытому Chrome
    с отладочным портом (`portal_cli.py chrome`).
    """
    pw = sync_playwright().start()

    if attach:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        return Session(page=page, _ctx=browser, _pw=pw)

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",          # настоящий Google Chrome, а не встроенный Chromium
        headless=headless,
        accept_downloads=True,
        downloads_path=str(downloads) if downloads else None,
        viewport=None,
        args=["--start-maximized"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return Session(page=page, _ctx=ctx, _pw=pw)


def is_logged_in(page: Page) -> bool:
    """Портал при разлогине редиректит на страницу входа."""
    url = page.url.lower()
    return "portal.example.com" in url and "login" not in url


def wait_for_login(session: Session, timeout_s: int = 600) -> None:
    """Открывает портал и ждёт, пока ты войдёшь руками."""
    page = session.page
    page.goto(BASE + "/uzon/", wait_until="domcontentloaded")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if is_logged_in(page) and page.locator("text=Заявки").count():
            print("Вход выполнен, профиль сохранён.")
            return
        time.sleep(2)
    raise TimeoutError("Вход не выполнен за отведённое время.")


def find_calc_button(page: Page):
    """Кнопка «Расчет». Ищем по тексту, класс GWT — только как запасной путь."""
    by_text = page.get_by_text("Расчет", exact=True)
    if by_text.count():
        return by_text.first
    by_class = page.locator(f"div.{LEGACY_CALC_CLASS}")
    if by_class.count():
        return by_class.first
    return None


REQUEST_ID_RE = re.compile(r"\b(\d{6,9})\b")


def visible_request_ids(page: Page) -> list[str]:
    """Номера заявок, видимые в текущем списке."""
    ids: list[str] = []
    for href in page.locator("a[href*='request']").evaluate_all(
        "els => els.map(e => e.getAttribute('href'))"
    ):
        m = REQUEST_ID_RE.search(href or "")
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def poll_for_new(session: Session, interval_s: int = 60, seen: set[str] | None = None):
    """Раз в interval_s жмёт «Расчет» и отдаёт номера новых заявок.

    Генератор: на каждой итерации отдаёт список новых номеров (может быть пустым),
    чтобы вызывающий код решал, что с ними делать.
    """
    seen = set() if seen is None else seen
    page = session.page
    while True:
        btn = find_calc_button(page)
        if btn is None:
            print("Кнопка «Расчет» не найдена. Портал перерисовали — нужен новый селектор.")
        else:
            btn.click()
            page.wait_for_timeout(3000)
        ids = visible_request_ids(page)
        new = [i for i in ids if i not in seen]
        seen.update(ids)
        yield new
        time.sleep(interval_s)
