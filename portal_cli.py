#!/usr/bin/env python3
"""Блок A: кликер по порталу Apex/Uzon. Только чтение и скачивание.

    python3 portal_cli.py login                 # один раз, вход руками
    python3 portal_cli.py watch                 # опрос «Расчет» раз в минуту
    python3 portal_cli.py fetch 1234567         # карточка заявки -> JSON
    python3 portal_cli.py dump 1234567          # сохранить HTML страницы

Все команды работают в настоящем Google Chrome с отдельным профилем
~/.auto-calc/chrome-profile. Флаг --attach подключается к уже открытому Chrome
вместо запуска нового.

Скрипт не вводит логин и пароль. Вход выполняется вручную командой login,
дальше сессия живёт в профиле ~/.auto-calc/profile.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import claim as claim_mod  # noqa: E402
import portal  # noqa: E402

OUT = Path(__file__).parent / "data" / "out"


def cmd_login(args) -> int:
    session = portal.open_session(attach=args.attach)
    try:
        print("Открыл портал. Войди в браузере — профиль сохранится.")
        portal.wait_for_login(session)
        return 0
    finally:
        session.close()


def cmd_watch(args) -> int:
    session = portal.open_session(attach=args.attach)
    try:
        if not portal.is_logged_in(session.page):
            portal.wait_for_login(session)
        print(f"Опрос «Расчет» раз в {args.interval} c. Ctrl+C — выход.")
        for new_ids in portal.poll_for_new(session, interval_s=args.interval):
            if not new_ids:
                continue
            print(f"Новые заявки: {', '.join(new_ids)}")
            for request_id in new_ids:
                data = claim_mod.fetch(session, request_id)
                path = claim_mod.save(data, OUT)
                _print_claim(data, path)
                if args.once:
                    return 0
    except KeyboardInterrupt:
        print("\nОстановлено.")
        return 0
    finally:
        session.close()


def cmd_fetch(args) -> int:
    session = portal.open_session(attach=args.attach)
    try:
        if not portal.is_logged_in(session.page):
            portal.wait_for_login(session)
        data = claim_mod.fetch(session, args.request_id)
        _print_claim(data, claim_mod.save(data, OUT))
        return 0
    finally:
        session.close()


def cmd_dump(args) -> int:
    """Сохраняет HTML карточки, чтобы уточнить селекторы по реальной странице."""
    session = portal.open_session(attach=args.attach)
    try:
        if not portal.is_logged_in(session.page):
            portal.wait_for_login(session)
        page = session.page
        page.goto(portal.REQUEST_URL.format(id=args.request_id), wait_until="networkidle")
        OUT.mkdir(parents=True, exist_ok=True)
        html = OUT / f"{args.request_id}_page.html"
        html.write_text(page.content(), encoding="utf-8")
        shot = OUT / f"{args.request_id}_page.png"
        page.screenshot(path=str(shot), full_page=True)
        print(f"HTML: {html}\nСкриншот: {shot}")
        return 0
    finally:
        session.close()


def _print_claim(data: dict, path: Path) -> None:
    f = data["fields"]
    print(f"Заявка {data['request_id']}: {data.get('claim_type') or 'тип не определён'}")
    print(f"  ТС: {f.get('make', '?')} {f.get('model', '')} {f.get('year', '')}")
    print(f"  Полис: {f.get('policy_number', '?')}  Убыток: {f.get('claim_number', '?')}")
    print(f"  Регион: {f.get('region', '?')}")
    print(f"  Место аварии: {data.get('accident_place_full') or '—'}")
    for c in data.get("comments", []):
        print(f"  Комментарий {c['at']} {c['author']}: {c['text']}")
    if data["missing"]:
        print(f"  Не найдены поля: {', '.join(data['missing'])}")
    print(f"  JSON: {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--attach", action="store_true",
                    help="подключиться к уже открытому Chrome вместо запуска нового")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login").set_defaults(fn=cmd_login)

    w = sub.add_parser("watch")
    w.add_argument("--interval", type=int, default=60)
    w.add_argument("--once", action="store_true", help="выйти после первой заявки")
    w.set_defaults(fn=cmd_watch)

    f = sub.add_parser("fetch")
    f.add_argument("request_id")
    f.set_defaults(fn=cmd_fetch)

    d = sub.add_parser("dump")
    d.add_argument("request_id")
    d.set_defaults(fn=cmd_dump)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
