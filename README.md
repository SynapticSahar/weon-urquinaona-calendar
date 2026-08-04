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
3. Click **Download selected classes**.
4. Import `my-weon-workouts.ics` into the calendar used by TickTick.

Selections are stored only in that browser. The public timetable refreshes automatically three times per day.

## Important limitation

GitHub Pages cannot write your private selections back to the server. The page therefore exports an `.ics` file rather than maintaining a private live subscription. A true editable subscription would require a small authenticated backend.
