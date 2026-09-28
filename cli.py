#!/usr/bin/env python3
"""Распознать акт осмотра из PDF в JSON.

    python3 cli.py "/Users/user/Documents/Акты/createpdf (11).pdf"
    python3 cli.py --map "/path/to.pdf"        # только карта страниц, без извлечения
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pages as pages_mod  # noqa: E402
import recognize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "out")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--limit", type=int, help="обработать только первые N страниц")
    ap.add_argument("--map", action="store_true", help="только классификация страниц")
    args = ap.parse_args()

    if not args.pdf.exists():
        print(f"нет файла: {args.pdf}", file=sys.stderr)
        return 1

    if args.map:
        client = recognize._client()
        for page in pages_mod.render(args.pdf, dpi=120)[: args.limit or 999]:
            info = recognize.classify(client, page)
            print(f"стр.{page.index + 1}: {info['kind']} поворот={info['rotation_needed']}")
        return 0

    result = recognize.recognize_pdf(args.pdf, dpi=args.dpi, limit=args.limit)
    path = recognize.save(result, args.out)

    v = result["vehicle"] or {}
    print(f"ТС: {v.get('make_model', '?')} {v.get('plate', '?')} VIN {v.get('vin', '?')}")
    print(f"Позиций: {len(result['damages'])}")
    for it in result["damages"]:
        marks = "".join(c for c, on in
                        (("З", it.get("replace")), ("Р", it.get("repair")), ("О", it.get("paint"))) if on)
        print(f"  {it.get('n')}. {it.get('part')} [{marks or '-'}] {it.get('damage', '')}")
    if result["needs_manual"]:
        print("\nРучная проверка:")
        for m in result["needs_manual"]:
            print("  !", m)
    print(f"\nJSON: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
