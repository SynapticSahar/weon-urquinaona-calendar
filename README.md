# We/On Urquinaona weekly planner

A small webpage that reads the public We/On Urquinaona timetable, lets you select any number of classes for each day, remembers the choices in the browser, and exports the selected classes as an `.ics` file for TickTick or another calendar app.

## First setup

1. Upload all files in this repository to the `main` branch.
2. Open **Settings → Pages** in GitHub.
3. Under **Build and deployment**, choose **GitHub Actions**.
4. Open **Actions → Update timetable and deploy site**.
5. Click **Run workflow**.
6. After it succeeds, open:

   `https://synapticsahar.github.io/weon-urquinaona-calendar/`

## Use with TickTick

1. Open the planner webpage.
2. Select as many classes as you want for each day.
3. Click **Sync to Google Calendar** if Google sync is configured, or click **Download selected classes** for a manual `.ics` export.
4. TickTick will receive synced Google Calendar events if your Google Calendar is connected in TickTick.

Selections are stored only in that browser. The public timetable refreshes automatically throughout the day.

## Google Calendar sync setup

The Google Calendar sync button uses Google OAuth directly in the browser. To enable it:

1. In Google Cloud Console, create an OAuth 2.0 Client ID for a **Web application**.
2. Add `https://synapticsahar.github.io` as an authorized JavaScript origin.
3. Enable the Google Calendar API for the same Google Cloud project.
4. Paste the client ID into `googleClientId` in `docs/index.html`.
5. In TickTick, subscribe to or integrate the same Google Calendar account.

The client ID is public configuration, not a password. Do not add any Google client secret to this static site.

## Important limitation

GitHub Pages cannot store your private selections on the server. The page keeps selections in your browser, then either exports an `.ics` file or writes selected classes to Google Calendar when you click **Sync to Google Calendar**. A private always-on subscription would still require a small authenticated backend.
# workflow trigger
