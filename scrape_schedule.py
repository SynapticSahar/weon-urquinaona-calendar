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
INVALID_CLASS_NAMES = {"Sala Cycle", "Zona Cross", "Zona Funcional"}


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


def is_invalid_class_name(name: str, room: str) -> bool:
    normalized_name = clean_text(name).casefold()
    normalized_room = clean_text(room).casefold()
    invalid_names = {value.casefold() for value in INVALID_CLASS_NAMES}
    return not normalized_name or normalized_name == normalized_room or normalized_name in invalid_names


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
              const normalize = value => (value || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
              const text = el => normalize(el.innerText);
              const lines = el => (el.innerText || '')
                .split(/\\n+/)
                .map(normalize)
                .filter(Boolean);
              const timeRe = /^\\d{2}:\\d{2}\\s*-\\s*\\d{2}:\\d{2}\\s*\\|/;
              const dayRe = /^(Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes|Sábado|Sabado|Domingo)\\s+\\d{1,2}\\/\\d{1,2}$/;
              const sameText = (a, b) => normalize(a).toLocaleLowerCase() === normalize(b).toLocaleLowerCase();
              const validNameLine = (line, timeRoom) => {
                const value = normalize(line);
                return value
                  && !sameText(value, timeRoom)
                  && !timeRe.test(value)
                  && !dayRe.test(value);
              };
              const uniqueLines = values => {
                const seen = new Set();
                const result = [];
                for (const value of values) {
                  const key = normalize(value).toLocaleLowerCase();
                  if (!key || seen.has(key)) continue;
                  seen.add(key);
                  result.push(normalize(value));
                }
                return result;
              };
              const tightContainer = (el, timeRoom) => {
                if (!el || el === document.body || !visible(el)) return false;
                const r = el.getBoundingClientRect();
                if (r.height > Math.max(300, window.innerHeight * 0.45)) return false;
                const elLines = uniqueLines(lines(el));
                const timeLines = elLines.filter(line => timeRe.test(line));
                return timeLines.length === 1
                  && sameText(timeLines[0], timeRoom)
                  && !elLines.some(line => dayRe.test(line));
              };
              const nameFromLines = (el, timeRoom) => {
                const elLines = uniqueLines(lines(el));
                const timeIndex = elLines.findIndex(line => timeRe.test(line) && sameText(line, timeRoom));
                if (timeIndex < 0) return '';
                const ordered = elLines.slice(timeIndex + 1).concat(elLines.slice(0, timeIndex));
                return ordered.find(line => validNameLine(line, timeRoom)) || '';
              };
              const nameFromSmallestText = (root, timeRoom) => {
                if (!root || !visible(root)) return '';
                const scoped = [root, ...root.querySelectorAll('*')].filter(visible);
                const smallest = scoped.filter(el => {
                  const possible = lines(el).some(line => validNameLine(line, timeRoom));
                  if (!possible) return false;
                  return ![...el.children]
                    .filter(visible)
                    .some(child => lines(child).some(line => validNameLine(line, timeRoom)));
                });
                for (const el of smallest) {
                  const name = lines(el).find(line => validNameLine(line, timeRoom));
                  if (name) return name;
                }
                return nameFromLines(root, timeRoom);
              };
              const nearbySiblingName = (cursor, timeRoom) => {
                const parent = cursor.parentElement;
                if (!parent || !tightContainer(parent, timeRoom)) return '';
                const siblings = [...parent.children].filter(visible);
                const index = siblings.indexOf(cursor);
                if (index < 0) return '';
                const offsets = [1, -1, 2, -2];
                for (const offset of offsets) {
                  const sibling = siblings[index + offset];
                  if (!sibling) continue;
                  const name = nameFromSmallestText(sibling, timeRoom);
                  if (name) return name;
                }
                return '';
              };
              const classFromTimeElement = timeEl => {
                const timeRoom = lines(timeEl).find(line => timeRe.test(line));
                if (!timeRoom) return null;

                let cursor = timeEl;
                for (let depth = 0; cursor && cursor !== document.body && depth < 8; depth += 1) {
                  const parent = cursor.parentElement;
                  if (!parent) break;

                  if (tightContainer(parent, timeRoom)) {
                    const siblingName = nearbySiblingName(cursor, timeRoom);
                    const name = siblingName || nameFromLines(parent, timeRoom);
                    if (name) {
                      const r = parent.getBoundingClientRect();
                      return {
                        time_room: normalize(timeRoom),
                        name: normalize(name),
                        x: r.x + r.width / 2,
                        y: r.y + scrollY,
                      };
                    }
                  }

                  cursor = parent;
                }

                return null;
              };
              const days = nodes
                .filter(el => dayRe.test(text(el)))
                .filter(el => ![...el.children].some(child => dayRe.test(text(child))))
                .map(el => { const r = el.getBoundingClientRect(); return {text: text(el), x: r.x + r.width/2, y: r.y + scrollY}; });

              const classes = nodes
                .filter(el => lines(el).some(line => timeRe.test(line)))
                .filter(el => ![...el.children].some(child => lines(child).some(line => timeRe.test(line))))
                .map(classFromTimeElement)
                .filter(Boolean);
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
        time_room = clean_text(raw_class["time_room"])
        match = CLASS_RE.match(time_room)
        if not match:
            continue
        start, end, room = match.groups()
        room = clean_text(room)
        name = clean_text(raw_class["name"])
        if is_invalid_class_name(name, room):
            continue

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


def print_sample_records(classes: list[ClassItem]) -> None:
    print("Sample extracted records:")
    for item in classes[:10]:
        print(f"  {item.date} {item.start} | {item.name} | {item.room}")


async def main() -> None:
    classes = await extract_schedule()
    print_sample_records(classes)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": URL,
        "club": "We/On",
        "timezone": TIMEZONE,
        "updated_at": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
        "classes": [asdict(item) for item in classes],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(classes)} classes to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
