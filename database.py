import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).with_name('productivity_buddy.db')

CATEGORIES = ('Study', 'Work', 'Personal', 'Health')
PRIORITIES = ('High', 'Medium', 'Low')


@contextmanager
def connect():
    """Open a connection, commit on success, and always close it.

    `with sqlite3.connect(...)` only manages the transaction - it never closes
    the connection - so the previous version leaked one connection per query.
    """
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Study',
            priority TEXT NOT NULL DEFAULT 'Medium',
            due_date TEXT DEFAULT '',
            estimate INTEGER NOT NULL DEFAULT 30,
            notes TEXT DEFAULT '',
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS focus_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            minutes INTEGER NOT NULL,
            day TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        count = db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        if count == 0:
            examples = [
                ('Review machine learning notes', 'Study', 'High', date.today().isoformat(), 45, 'Focus on the concepts that still feel unclear.', 0),
                ('Finish project README', 'Work', 'Medium', date.today().isoformat(), 30, 'Add setup steps and a short feature overview.', 0),
                ('Take a proper screen break', 'Health', 'Low', '', 15, 'Stretch, drink water, and rest your eyes.', 0),
            ]
            db.executemany('INSERT INTO tasks (title, category, priority, due_date, estimate, notes, completed) VALUES (?, ?, ?, ?, ?, ?, ?)', examples)


def get_tasks():
    with connect() as db:
        rows = db.execute('''SELECT * FROM tasks ORDER BY completed ASC,
            CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
            CASE WHEN due_date IS NULL OR due_date = '' THEN 1 ELSE 0 END, due_date ASC, id DESC''').fetchall()
        return [dict(row) for row in rows]


def get_task_by_id(task_id):
    with connect() as db:
        row = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        return dict(row) if row else None


def add_task(title, category, priority, due_date, estimate, notes):
    category = category if category in CATEGORIES else 'Study'
    priority = priority if priority in PRIORITIES else 'Medium'
    with connect() as db:
        db.execute('INSERT INTO tasks (title, category, priority, due_date, estimate, notes) VALUES (?, ?, ?, ?, ?, ?)',
                   (title, category, priority, due_date, estimate, notes))


def update_task_status(task_id, completed):
    with connect() as db:
        db.execute('UPDATE tasks SET completed = ? WHERE id = ?', (int(bool(completed)), task_id))


def delete_task(task_id):
    with connect() as db:
        db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))


def log_focus_session(minutes, task_id=None):
    if task_id is not None and not get_task_by_id(task_id):
        task_id = None
    with connect() as db:
        db.execute('INSERT INTO focus_sessions (task_id, minutes, day) VALUES (?, ?, ?)',
                   (task_id, minutes, date.today().isoformat()))


def focus_summary(day=None):
    day = day or date.today().isoformat()
    with connect() as db:
        row = db.execute('SELECT COUNT(*) AS sessions, COALESCE(SUM(minutes), 0) AS minutes FROM focus_sessions WHERE day = ?',
                         (day,)).fetchone()
        return {'sessions': row['sessions'], 'minutes': row['minutes']}


def rescue_plan(available_minutes):
    """Create a transparent, priority-first recovery plan from unfinished tasks."""
    tasks = [task for task in get_tasks() if not task['completed']]
    today = date.today().isoformat()
    priority_rank = {'High': 0, 'Medium': 1, 'Low': 2}
    tasks.sort(key=lambda task: (
        0 if task['due_date'] and task['due_date'] < today else 1,
        priority_rank.get(task['priority'], 1),
        0 if task['due_date'] == today else 1,
        task['due_date'] or '9999-12-31',
        task['estimate'],
    ))
    chosen, deferred = [], []
    remaining = available_minutes
    for task in tasks:
        if task['estimate'] <= remaining:
            chosen.append(task)
            remaining -= task['estimate']
        else:
            deferred.append(task)
    return {'chosen': chosen, 'deferred': deferred, 'remaining': remaining,
            'total_planned': available_minutes - remaining,
            'all_count': len(tasks), 'empty': not tasks}
