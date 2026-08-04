from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

URL = "https://www.weonclub.com/horarios-clases?club=17"
OUTPUT = Path("docs/schedule.json")
TIMEZONE = "Europe/Madrid"
DAY_RE = re.compile(r"^(Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes|Sábado|Sabado|Domingo)\s+(\d{1,2})/(\d{1,2})$")
CLASS_RE = re.compile(r"^(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*\|\s*(.+)$", re.S)


@dataclass(frozen=True)
class ClassItem:
    id: str
    date: str
    day: str
    start: str
    end: str
    room: str
    name: str


def resolve_year(day: int, month: int, now: datetime) -> int:
    candidate = datetime(now.year, month, day, tzinfo=now.tzinfo)
    delta = (candidate.date() - now.date()).days
    if delta < -120:
        return now.year + 1
    if delta > 300:
        return now.year - 1
    return now.year


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


async def extract_schedule() -> list[ClassItem]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 1200})
        await page.goto(URL, wait_until="networkidle", timeout=90_000)
        await page.wait_for_timeout(2_000)

        raw = await page.evaluate(
            """
            () => {
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const nodes = [...document.querySelectorAll('body *')].filter(visible);
              const text = el => (el.innerText || '').replace(/\s+/g, ' ').trim();
              const days = nodes
                .filter(el => /^(Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes|Sábado|Sabado|Domingo)\s+\d{1,2}\/\d{1,2}$/.test(text(el)))
                .filter(el => ![...el.children].some(child => /^(Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes|Sábado|Sabado|Domingo)\s+\d{1,2}\/\d{1,2}$/.test(text(child))))
                .map(el => { const r = el.getBoundingClientRect(); return {text: text(el), x: r.x + r.width/2, y: r.y + scrollY}; });

              const classes = nodes
                .filter(el => /^\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\s*\|/.test(text(el)))
                .filter(el => ![...el.children].some(child => /^\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\s*\|/.test(text(child))))
                .map(el => { const r = el.getBoundingClientRect(); return {text: text(el), x: r.x + r.width/2, y: r.y + scrollY}; });
              return {days, classes};
            }
            """
        )
        await browser.close()

    day_headers = []
    for item in raw["days"]:
        match = DAY_RE.match(clean_text(item["text"]))
        if match:
            day_headers.append({**item, "match": match.groups()})

    if not day_headers:
        raise RuntimeError("No dated day headers found. The We/On page structure may have changed.")

    now = datetime.now(ZoneInfo(TIMEZONE))
    results: dict[str, ClassItem] = {}

    for raw_class in raw["classes"]:
        text = clean_text(raw_class["text"])
        match = CLASS_RE.match(text)
        if not match:
            continue
        start, end, remainder = match.groups()

        eligible = [header for header in day_headers if header["y"] <= raw_class["y"] + 80]
        if not eligible:
            continue
        nearest_row_y = max(header["y"] for header in eligible)
        row_headers = [header for header in day_headers if abs(header["y"] - nearest_row_y) < 60]
        header = min(row_headers, key=lambda value: abs(value["x"] - raw_class["x"]))

        day_name, day_text, month_text = header["match"]
        day = int(day_text)
        month = int(month_text)
        year = resolve_year(day, month, now)
        date_value = f"{year:04d}-{month:02d}-{day:02d}"

        # The room is separated from the class name visually. Common room prefixes
        # are handled first, then a conservative final-word split is used.
        room_names = [
            "Zona Cross", "Zona Funcional", "Sala Cycle", "Studio 1", "Studio 2",
            "Piscina", "Exterior", "Terraza"
        ]
        room = "We/On Urquinaona"
        name = remainder
        for candidate in room_names:
            if remainder.casefold().startswith(candidate.casefold() + " "):
                room = candidate
                name = remainder[len(candidate):].strip()
                break

        name = clean_text(name)
        if not name:
            continue
        item_id = f"{date_value}-{start}-{end}-{name}-{room}".casefold()
        item_id = re.sub(r"[^a-z0-9]+", "-", item_id).strip("-")
        results[item_id] = ClassItem(
            id=item_id,
            date=date_value,
            day=day_name,
            start=start,
            end=end,
            room=room,
            name=name,
        )

    classes = sorted(results.values(), key=lambda value: (value.date, value.start, value.name))
    if len(classes) < 20:
        raise RuntimeError(f"Only {len(classes)} classes were extracted. Refusing to overwrite the schedule.")
    return classes


async def main() -> None:
    classes = await extract_schedule()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": URL,
        "club": "We/On Urquinaona",
        "timezone": TIMEZONE,
        "updated_at": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
        "classes": [asdict(item) for item in classes],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(classes)} classes to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
