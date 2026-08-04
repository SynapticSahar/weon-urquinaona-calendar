const STORAGE_KEY = "weon-urquinaona-selected-v1";
const dayOrder = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const dayMap = {
  Lunes: "Monday", Martes: "Tuesday", Miércoles: "Wednesday", Miercoles: "Wednesday",
  Jueves: "Thursday", Viernes: "Friday", Sábado: "Saturday", Sabado: "Saturday", Domingo: "Sunday"
};

let data = null;
let selected = new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));

const scheduleEl = document.querySelector("#schedule");
const statusEl = document.querySelector("#status");
const searchEl = document.querySelector("#search");
const timeFilterEl = document.querySelector("#timeFilter");
const weekFilterEl = document.querySelector("#weekFilter");
const countEl = document.querySelector("#selectionCount");

function localDate(date) {
  return new Date(`${date}T12:00:00`);
}

function mondayOf(date) {
  const value = localDate(date);
  const day = value.getDay() || 7;
  value.setDate(value.getDate() - day + 1);
  return value.toISOString().slice(0, 10);
}

function prettyDate(date) {
  return localDate(date).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function saveSelection() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...selected]));
  countEl.textContent = `${selected.size} class${selected.size === 1 ? "" : "es"} selected`;
}

function timeMatches(start, filter) {
  const hour = Number(start.slice(0, 2));
  if (filter === "morning") return hour < 12;
  if (filter === "afternoon") return hour >= 12 && hour < 17;
  if (filter === "evening") return hour >= 17;
  return true;
}

function render() {
  const week = weekFilterEl.value;
  const query = searchEl.value.trim().toLocaleLowerCase();
  const time = timeFilterEl.value;
  const weekClasses = data.classes.filter(item => mondayOf(item.date) === week);
  const dates = [...new Set(weekClasses.map(item => item.date))].sort();
  scheduleEl.replaceChildren();

  for (const date of dates) {
    const allForDay = weekClasses.filter(item => item.date === date);
    const visible = allForDay.filter(item => {
      const text = `${item.name} ${item.room}`.toLocaleLowerCase();
      return (!query || text.includes(query)) && timeMatches(item.start, time);
    });
    const day = document.createElement("article");
    day.className = "day";
    const englishDay = dayMap[allForDay[0]?.day] || localDate(date).toLocaleDateString("en-GB", { weekday: "long" });
    day.innerHTML = `
      <div class="day-header">
        <div><h2>${englishDay}</h2><p>${prettyDate(date)}</p></div>
        <button type="button" data-clear-day="${date}">Clear</button>
      </div>
      <div class="class-list"></div>`;
    const list = day.querySelector(".class-list");

    if (!visible.length) {
      list.innerHTML = '<div class="empty">No matching classes.</div>';
    }

    for (const item of visible) {
      const label = document.createElement("label");
      label.className = `class-card${selected.has(item.id) ? " selected" : ""}`;
      label.innerHTML = `
        <div class="class-row">
          <input type="checkbox" ${selected.has(item.id) ? "checked" : ""}>
          <span class="class-time"></span>
          <span class="class-separator">|</span>
          <strong class="class-name"></strong>
          <span class="class-separator">|</span>
          <span class="class-room"></span>
        </div>`;
      label.querySelector(".class-time").textContent = item.start;
      label.querySelector(".class-name").textContent = item.name;
      label.querySelector(".class-room").textContent = item.room;
      label.querySelector("input").addEventListener("change", event => {
        event.target.checked ? selected.add(item.id) : selected.delete(item.id);
        label.classList.toggle("selected", event.target.checked);
        saveSelection();
      });
      list.append(label);
    }
    scheduleEl.append(day);
  }
  saveSelection();
}

function escapeIcs(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;");
}

function dateTime(date, time) {
  return `${date.replaceAll("-", "")}T${time.replace(":", "")}00`;
}

function downloadSelected() {
  const classes = data.classes.filter(item => selected.has(item.id)).sort((a, b) => `${a.date}${a.start}`.localeCompare(`${b.date}${b.start}`));
  if (!classes.length) {
    alert("Select at least one class first.");
    return;
  }
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//WeOn Weekly Planner//EN",
    "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:My We/On Workouts",
    "X-WR-TIMEZONE:Europe/Madrid"
  ];
  for (const item of classes) {
    lines.push(
      "BEGIN:VEVENT",
      `UID:${item.id}@weon-urquinaona-calendar`,
      `DTSTAMP:${stamp}`,
      `DTSTART;TZID=Europe/Madrid:${dateTime(item.date, item.start)}`,
      `DTEND;TZID=Europe/Madrid:${dateTime(item.date, item.end)}`,
      `SUMMARY:${escapeIcs(item.name)}`,
      `LOCATION:${escapeIcs(item.room)}`,
      `DESCRIPTION:${escapeIcs("Selected with We/On Weekly Planner")}`,
      "END:VEVENT"
    );
  }
  lines.push("END:VCALENDAR");
  const blob = new Blob([lines.join("\r\n") + "\r\n"], { type: "text/calendar;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "my-weon-workouts.ics";
  link.click();
  URL.revokeObjectURL(link.href);
}

async function init() {
  try {
    const response = await fetch(`schedule.json?v=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    data = await response.json();
    const validIds = new Set(data.classes.map(item => item.id));
    selected = new Set([...selected].filter(id => validIds.has(id)));

    const weeks = [...new Set(data.classes.map(item => mondayOf(item.date)))].sort();
    for (const week of weeks) {
      const option = document.createElement("option");
      option.value = week;
      const end = localDate(week); end.setDate(end.getDate() + 6);
      option.textContent = `${prettyDate(week)} – ${prettyDate(end.toISOString().slice(0, 10))}`;
      weekFilterEl.append(option);
    }
    const todayWeek = mondayOf(new Date().toISOString().slice(0, 10));
    weekFilterEl.value = weeks.includes(todayWeek) ? todayWeek : weeks[0];
    statusEl.textContent = `Updated ${new Date(data.updated_at).toLocaleString()}`;
    render();
  } catch (error) {
    console.error(error);
    statusEl.textContent = "Schedule unavailable";
    scheduleEl.innerHTML = '<div class="toolbar">The schedule has not been generated yet. Run the GitHub Action once.</div>';
  }
}

searchEl.addEventListener("input", render);
timeFilterEl.addEventListener("change", render);
weekFilterEl.addEventListener("change", render);
document.querySelector("#downloadIcs").addEventListener("click", downloadSelected);
document.querySelector("#clearWeek").addEventListener("click", () => {
  const week = weekFilterEl.value;
  for (const item of data.classes) if (mondayOf(item.date) === week) selected.delete(item.id);
  render();
});
scheduleEl.addEventListener("click", event => {
  const button = event.target.closest("[data-clear-day]");
  if (!button) return;
  for (const item of data.classes) if (item.date === button.dataset.clearDay) selected.delete(item.id);
  render();
});

init();
