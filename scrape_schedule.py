from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

URL = "https://www.weonclub.com/horarios-clases?club=17"
OUTPUT = Path("docs/schedule.json")
TIMEZONE = "Europe/Madrid"
DAY_RE = re.compile(r"^(Lunes|Martes|Miércoles|Miercoles|Jueves|Viernes|Sábado|Sabado|Domingo)\s+(\d{1,2})/(\d{1,2})$")
CLASS_RE = re.compile(r"^(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*\|\s*(.+)$", re.S)
INVALID_CLASS_NAMES = {"Sala Cycle", "Zona Cross", "Zona Funcional"}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass(frozen=True)
class ClassItem:
    id: str
    date: str
    day: str
    start: str
    end: str
    room: str
    name: str


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    children: list["Node"] = field(default_factory=list)
    parts: list[str | "Node"] = field(default_factory=list)
    parent: "Node | None" = None

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def has_class(self, value: str) -> bool:
        return value in self.classes

    def text(self) -> str:
        values: list[str] = []

        def walk(node: Node) -> None:
            for part in node.parts:
                if isinstance(part, Node):
                    walk(part)
                else:
                    values.append(part)

        walk(self)
        return clean_text("".join(values))

    def descendants(self) -> list["Node"]:
        values: list[Node] = []

        def walk(node: Node) -> None:
            for child in node.children:
                values.append(child)
                walk(child)

        walk(self)
        return values

    def find_all(self, predicate) -> list["Node"]:
        return [node for node in self.descendants() if predicate(node)]


class ScheduleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {key: value or "" for key, value in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        self.stack[-1].parts.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].parts.append(data)


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


def fetch_html() -> str:
    request = Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; WeOnScheduleBot/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=90) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def parse_html(html: str) -> Node:
    parser = ScheduleHTMLParser()
    parser.feed(html)
    return parser.root


def is_schedule_table(node: Node) -> bool:
    return node.tag == "div" and {"schedule-table", "schedule-table-17"}.issubset(node.classes)


def is_day_header(node: Node) -> bool:
    return node.tag == "div" and node.has_class("schedule-table-days")


def is_schedule_row(node: Node) -> bool:
    return node.tag == "div" and node.has_class("schedule-table__content") and node.has_class("filter-by-class-row")


def is_empty_cell(node: Node) -> bool:
    return node.tag == "div" and node.has_class("schedule-empty-cell")


def is_class_cell(node: Node) -> bool:
    return node.tag == "div" and node.has_class("filter-by-class") and not node.has_class("filter-by-class-empty")


def first_descendant_text(node: Node, tag: str, class_name: str) -> str:
    matches = [item for item in node.descendants() if item.tag == tag and item.has_class(class_name)]
    return matches[0].text() if matches else ""


def parse_class_cell(cell: Node) -> tuple[str, str, str, str] | None:
    time_room = first_descendant_text(cell, "span", "gray")
    name = first_descendant_text(cell, "span", "text-class")
    match = CLASS_RE.match(time_room)
    if not match:
        return None
    start, end, room = match.groups()
    room = clean_text(room)
    name = clean_text(name)
    if is_invalid_class_name(name, room):
        return None
    return start, end, room, name


def item_id_for(date_value: str, start: str, end: str, name: str, room: str) -> str:
    item_id = f"{date_value}-{start}-{end}-{name}-{room}".casefold()
    return re.sub(r"[^a-z0-9]+", "-", item_id).strip("-")


def class_items_from_table(table: Node, now: datetime) -> list[ClassItem]:
    day_headers = []
    for node in table.find_all(is_day_header):
        text = node.text()
        match = DAY_RE.match(text)
        if not match:
            continue
        day_name, day_text, month_text = match.groups()
        day = int(day_text)
        month = int(month_text)
        year = resolve_year(day, month, now)
        day_headers.append(
            {
                "day_name": day_name,
                "date": f"{year:04d}-{month:02d}-{day:02d}",
            }
        )

    if not day_headers:
        return []

    items: list[ClassItem] = []
    rows = [child for child in table.children if is_schedule_row(child)]
    for row in rows:
        children = [child for child in row.children if child.tag == "div"]
        day_index = 0
        index = 0
        while index < len(children) and day_index < len(day_headers):
            node = children[index]
            class_cell = None

            if is_empty_cell(node) and index + 1 < len(children) and is_class_cell(children[index + 1]):
                class_cell = children[index + 1]
                index += 2
            else:
                if is_class_cell(node):
                    class_cell = node
                index += 1

            if class_cell is not None:
                parsed = parse_class_cell(class_cell)
                if parsed is not None:
                    start, end, room, name = parsed
                    day = day_headers[day_index]
                    item_id = item_id_for(day["date"], start, end, name, room)
                    items.append(
                        ClassItem(
                            id=item_id,
                            date=day["date"],
                            day=day["day_name"],
                            start=start,
                            end=end,
                            room=room,
                            name=name,
                        )
                    )

            day_index += 1

    return items


def extract_schedule() -> list[ClassItem]:
    root = parse_html(fetch_html())
    now = datetime.now(ZoneInfo(TIMEZONE))
    results: dict[str, ClassItem] = {}

    for table in root.find_all(is_schedule_table):
        for item in class_items_from_table(table, now):
            results[item.id] = item

    classes = sorted(results.values(), key=lambda value: (value.date, value.start, value.name, value.room))
    if len(classes) < 20:
        raise RuntimeError(f"Only {len(classes)} classes were extracted. Refusing to overwrite the schedule.")
    return classes


def print_sample_records(classes: list[ClassItem]) -> None:
    print("Sample extracted records:")
    for item in classes[:10]:
        print(f"  {item.date} {item.start} | {item.name} | {item.room}")


def print_validation_records(classes: list[ClassItem]) -> None:
    print("Validation examples:")
    wanted = [
        ("13:00", "XPRESS GLÚTEO", "Zona Cross"),
        ("13:00", "VIRTUAL CYCLE", "Sala Cycle"),
    ]
    for start, name, room in wanted:
        match = next((item for item in classes if item.start == start and item.name == name and item.room == room), None)
        if match is None:
            raise RuntimeError(f"Missing expected class: {start} | {name} | {room}")
        print(f"  {match.date} {match.start}-{match.end} | {match.name} | {match.room}")


def main() -> None:
    classes = extract_schedule()
    print_sample_records(classes)
    print_validation_records(classes)
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
    main()
