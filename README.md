# Productivity Buddy

**Plan with intention. Recover without guilt.**

Productivity Buddy is a student-focused task planner built around one idea: when a day goes off-plan, people need a practical recovery plan—not another reason to feel behind.

## What makes it different

- **Rescue My Day:** enter the time you have left and receive a transparent focus list based on overdue work, priority, deadlines, and estimated duration.
- **Useful task details:** categories, priorities, due dates, estimates, and personal notes.
- **Progress overview:** counts, completion percentage, outstanding estimated time, and category summaries.
- **Search and filters:** quickly find tasks and separate active work from completed work.
- **Persistent storage:** SQLite keeps tasks between restarts.
- **Focus timer:** Pomodoro-style focus / short break / long break cycle with an animated ring, adjustable lengths, a chime, desktop notifications, and a link to any task. It keeps running across page reloads and logs completed focus minutes to SQLite.
- **Light & dark theme:** toggle in the top bar (or press `T`); follows your system setting until you choose, and remembers your choice.
- **Keyboard shortcuts:** `N` new task, `Space` start/pause timer, `/` search, `T` theme, `Esc` close.
- **Responsive UI:** sidebar navigation on desktop, compact navigation on mobile, and a keyboard-friendly task form.

## Stack

- Python and Flask
- SQLite
- HTML, CSS, Jinja2 templates
- Vanilla JavaScript for small interface interactions

The first version does **not** call an LLM API. The recovery planner is a deterministic, explainable algorithm, not an AI model. This keeps the app usable without API credentials and avoids representing rule-based logic as generative AI. An LLM integration can be added later with clear labeling and user-controlled input.

## Run locally

Python 3.10+ recommended.

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Project structure

```text
productivity-buddy/
├── app.py                 # Flask routes and page metrics
├── database.py            # SQLite schema and task/recovery logic
├── requirements.txt
├── README.md
├── BUILD_LOG.md           # Keep this honest and update during the event
├── .gitignore
├── templates/
│   ├── base.html          # Shared head, theme bootstrap, toasts
│   ├── _theme_toggle.html # Light/dark switch
│   ├── index.html         # Dashboard, focus timer, add-task dialog
│   └── rescue.html        # Recovery plan result
└── static/
    ├── style.css          # Themed (light/dark) responsive design system
    └── app.js             # Theme, focus timer, search, filters, modal, nav
```

## Manual test checklist

- [ ] Dashboard loads and seeded tasks are visible.
- [ ] Add a task with a title, category, priority, estimate, and optional deadline.
- [ ] Complete a task; counters and progress update after the page reloads.
- [ ] Delete a task and verify it disappears.
- [ ] Search tasks and try All / To do / Completed filters.
- [ ] Submit Rescue My Day with 60 minutes and confirm the plan never exceeds the available time.
- [ ] Try a very short time block and confirm tasks that do not fit are deferred.
- [ ] Restart Flask and confirm tasks remain saved.
- [ ] Check layout at desktop and mobile widths.
- [ ] Open `/health` and verify it returns `{"status":"ok","app":"Productivity Buddy"}`.

## Before deployment

- Set the `SECRET_KEY` environment variable (a random key is generated if it is missing).
- Set `FLASK_DEBUG=0` to turn off debug mode.
- Add CSRF protection and authentication if multiple users or public deployment are introduced.
- Do not collect sensitive personal information.

## Originality and responsible AI note

This implementation was created for the Productivity Buddy concept. The design, wording, task workflow, and recovery logic are specific to this project. Common web technologies and patterns are used; that does not guarantee any external plagiarism checker result. During the hackathon, update `BUILD_LOG.md` with actual work, decisions, bugs, challenge-card changes, and tools used. Follow the organizer's rules and disclose AI assistance as requested.

## Challenge-card adaptation strategy

1. Read the card and write down the exact new constraint.
2. Identify which user flow must change and what can stay.
3. Prefer a small, tested change over a rewrite.
4. Record the decision and trade-off in `BUILD_LOG.md`.
5. Re-test task creation, completion, persistence, and Rescue My Day before shipping.
