const STORAGE_KEY = "weon-urquinaona-selected-v1";
const GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events";
const GOOGLE_SYNC_SOURCE = "weon-weekly-planner";
const BASE32_HEX = "0123456789abcdefghijklmnopqrstuv";
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
const syncGoogleEl = document.querySelector("#syncGoogle");
const syncStatusEl = document.querySelector("#syncStatus");

let googleAccessToken = "";
let googleAccessTokenExpiresAt = 0;

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
  syncGoogleEl.disabled = selected.size === 0;
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

function selectedClasses() {
  return data.classes
    .filter(item => selected.has(item.id))
    .sort((a, b) => `${a.date}${a.start}`.localeCompare(`${b.date}${b.start}`));
}

function downloadSelected() {
  const classes = selectedClasses();
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

function googleConfig() {
  return {
    clientId: (window.WEON_CONFIG?.googleClientId || "").trim(),
    calendarId: (window.WEON_CONFIG?.googleCalendarId || "primary").trim() || "primary",
  };
}

function setSyncStatus(message, isError = false) {
  syncStatusEl.textContent = message;
  syncStatusEl.classList.toggle("error", isError);
}

function waitForGoogleIdentity() {
  if (window.google?.accounts?.oauth2) return Promise.resolve();

  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const timer = setInterval(() => {
      if (window.google?.accounts?.oauth2) {
        clearInterval(timer);
        resolve();
      } else if (Date.now() - startedAt > 10_000) {
        clearInterval(timer);
        reject(new Error("Google sign-in did not load. Refresh the page and try again."));
      }
    }, 100);
  });
}

function hasUsableGoogleToken() {
  return googleAccessToken && Date.now() < googleAccessTokenExpiresAt - 60_000;
}

function googleTokenError(response, fallback) {
  const error = new Error(response?.error_description || response?.message || response?.type || response?.error || fallback);
  error.code = response?.error || response?.type || "";
  return error;
}

function requestGoogleAccessToken(clientId, prompt) {
  return new Promise((resolve, reject) => {
    const client = google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: GOOGLE_CALENDAR_SCOPE,
      callback: response => {
        if (response.error) {
          reject(googleTokenError(response, response.error));
          return;
        }
        googleAccessToken = response.access_token;
        googleAccessTokenExpiresAt = Date.now() + Number(response.expires_in || 3600) * 1000;
        resolve(googleAccessToken);
      },
      error_callback: error => reject(googleTokenError(error, "Google sign-in was cancelled.")),
    });

    client.requestAccessToken({ prompt });
  });
}

async function authorizeGoogleCalendar() {
  const { clientId } = googleConfig();
  if (!clientId) {
    throw new Error("Add a Google OAuth client ID in docs/index.html to enable calendar sync.");
  }

  await waitForGoogleIdentity();

  if (hasUsableGoogleToken()) return googleAccessToken;

  try {
    return await requestGoogleAccessToken(clientId, "");
  } catch (silentError) {
    setSyncStatus("Google needs permission again...");
    return requestGoogleAccessToken(clientId, "consent");
  }
}

async function googleCalendarRequest(path, options = {}) {
  const response = await fetch(`https://www.googleapis.com/calendar/v3/${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${googleAccessToken}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (response.status === 204) return null;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(payload?.error?.message || `Google Calendar request failed with HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function base32Hex(value) {
  const bytes = new TextEncoder().encode(value);
  let bits = "";
  let output = "";

  for (const byte of bytes) {
    bits += byte.toString(2).padStart(8, "0");
    while (bits.length >= 5) {
      output += BASE32_HEX[parseInt(bits.slice(0, 5), 2)];
      bits = bits.slice(5);
    }
  }

  if (bits) output += BASE32_HEX[parseInt(bits.padEnd(5, "0"), 2)];
  return output;
}

function googleEventId(item) {
  return `a${base32Hex(`weon-${item.id}`).slice(0, 180)}`;
}

function googleDateTime(item, time) {
  return `${item.date}T${time}:00`;
}

function googleEventPayload(item) {
  const timezone = data.timezone || "Europe/Madrid";
  return {
    summary: `${item.name} | ${item.room}`,
    location: item.room,
    description: `${item.start} | ${item.name} | ${item.room}\nSynced from Weekly Planner.`,
    start: { dateTime: googleDateTime(item, item.start), timeZone: timezone },
    end: { dateTime: googleDateTime(item, item.end), timeZone: timezone },
    extendedProperties: {
      private: {
        source: GOOGLE_SYNC_SOURCE,
        classId: item.id,
      },
    },
    reminders: { useDefault: true },
  };
}

function calendarRange() {
  const dates = [...new Set(data.classes.map(item => item.date))].sort();
  const start = new Date(`${dates[0]}T00:00:00`);
  const end = new Date(`${dates[dates.length - 1]}T23:59:59`);
  return { timeMin: start.toISOString(), timeMax: end.toISOString() };
}

async function listSyncedGoogleEvents() {
  const { calendarId } = googleConfig();
  const params = new URLSearchParams({
    ...calendarRange(),
    maxResults: "2500",
    singleEvents: "true",
    showDeleted: "false",
  });
  params.append("privateExtendedProperty", `source=${GOOGLE_SYNC_SOURCE}`);

  const payload = await googleCalendarRequest(`calendars/${encodeURIComponent(calendarId)}/events?${params}`);
  return payload.items || [];
}

async function removeDeselectedGoogleEvents(selectedIds) {
  const { calendarId } = googleConfig();
  const events = await listSyncedGoogleEvents();
  const stale = events.filter(event => {
    const classId = event.extendedProperties?.private?.classId;
    return classId && !selectedIds.has(classId);
  });

  for (const event of stale) {
    await googleCalendarRequest(`calendars/${encodeURIComponent(calendarId)}/events/${encodeURIComponent(event.id)}`, {
      method: "DELETE",
    });
  }

  return stale.length;
}

async function upsertGoogleEvent(item) {
  const { calendarId } = googleConfig();
  const eventId = googleEventId(item);
  const calendarPath = `calendars/${encodeURIComponent(calendarId)}/events`;
  const event = { id: eventId, ...googleEventPayload(item) };

  try {
    await googleCalendarRequest(calendarPath, {
      method: "POST",
      body: JSON.stringify(event),
    });
  } catch (error) {
    if (error.status !== 409) throw error;
    await googleCalendarRequest(`${calendarPath}/${eventId}`, {
      method: "PUT",
      body: JSON.stringify(event),
    });
  }
}

async function syncSelectedToGoogle() {
  const classes = selectedClasses();
  if (!classes.length) {
    alert("Select at least one class first.");
    return;
  }

  const originalText = syncGoogleEl.textContent;
  syncGoogleEl.disabled = true;
  syncGoogleEl.textContent = "Syncing...";
  setSyncStatus("Connecting to Google Calendar...");

  try {
    await authorizeGoogleCalendar();
    const selectedIds = new Set(classes.map(item => item.id));
    const removed = await removeDeselectedGoogleEvents(selectedIds);

    for (let index = 0; index < classes.length; index += 1) {
      await upsertGoogleEvent(classes[index]);
      setSyncStatus(`Syncing ${index + 1}/${classes.length} classes...`);
    }

    const removedText = removed ? ` Removed ${removed} deselected class${removed === 1 ? "" : "es"}.` : "";
    setSyncStatus(`Synced ${classes.length} class${classes.length === 1 ? "" : "es"} to Google Calendar.${removedText}`);
  } catch (error) {
    console.error(error);
    setSyncStatus(error.message, true);
  } finally {
    syncGoogleEl.textContent = originalText;
    syncGoogleEl.disabled = selected.size === 0;
  }
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
syncGoogleEl.addEventListener("click", syncSelectedToGoogle);
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
