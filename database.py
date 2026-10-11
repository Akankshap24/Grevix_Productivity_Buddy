import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name('productivity_buddy.db')

CATEGORIES = ('Study', 'Work', 'Personal', 'Health')
PRIORITIES = ('High', 'Medium', 'Low')

# SQLite INTEGER is a signed 64-bit value; larger Python ints raise OverflowError.
MAX_SQLITE_INT = 2 ** 63 - 1

# Bumped when a migration runs; stored in PRAGMA user_version.
SCHEMA_VERSION = 2


def valid_id(value):
    """True if value can be used as a row id without overflowing SQLite."""
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_SQLITE_INT


def normalize_date(value):
    """Return a zero-padded YYYY-MM-DD string, '' for blank, or None if invalid.

    Dates are compared as text throughout the app, so they must always be
    stored zero-padded ('2026-02-01', never '2026-2-1').
    """
    if value is None:
        return ''
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return ''
    try:
        return datetime.strptime(value, '%Y-%m-%d').date().isoformat()
    except ValueError:
        return None


@contextmanager
def connect():
    """Open a database connection and safely manage transactions."""
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _columns(db, table):
    return {row['name'] for row in db.execute(f'PRAGMA table_info({table})').fetchall()}


def init_db():
    """Create tables and safely migrate existing databases."""
    with connect() as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]

        db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Study',
                priority TEXT NOT NULL DEFAULT 'Medium',
                due_date TEXT DEFAULT '',
                estimate INTEGER NOT NULL DEFAULT 30,
                notes TEXT DEFAULT '',
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                operation_id TEXT UNIQUE
            )
        ''')

        # Add operation_id to databases created before offline sync existed.
        if 'operation_id' not in _columns(db, 'tasks'):
            db.execute('ALTER TABLE tasks ADD COLUMN operation_id TEXT')

        db.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_operation_id
            ON tasks(operation_id)
        ''')

        db.execute('''
            CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                minutes INTEGER NOT NULL,
                day TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                session_key TEXT
            )
        ''')

        # session_key lets the server ignore the same timer being logged twice
        # (two open tabs, or a retried request).
        if 'session_key' not in _columns(db, 'focus_sessions'):
            db.execute('ALTER TABLE focus_sessions ADD COLUMN session_key TEXT')

        db.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_focus_sessions_key
            ON focus_sessions(session_key)
        ''')

        # Repair due dates saved without zero padding by older versions.
        for row in db.execute("SELECT id, due_date FROM tasks WHERE due_date IS NOT NULL AND due_date != ''").fetchall():
            fixed = normalize_date(row['due_date'])
            if fixed != row['due_date']:
                db.execute('UPDATE tasks SET due_date = ? WHERE id = ?', (fixed or '', row['id']))

        # Seed examples only on a brand-new database. Previously this ran
        # whenever the table was empty, so deleting every task and restarting
        # brought the samples back.
        if version == 0:
            count = db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
            if count == 0:
                today = date.today().isoformat()
                db.executemany('''
                    INSERT INTO tasks
                    (title, category, priority, due_date, estimate, notes, completed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', [
                    ('Review machine learning notes', 'Study', 'High', today, 45,
                     'Focus on the concepts that still feel unclear.', 0),
                    ('Finish project README', 'Work', 'Medium', today, 30,
                     'Add setup steps and a short feature overview.', 0),
                    ('Take a proper screen break', 'Health', 'Low', '', 15,
                     'Stretch, drink water, and rest your eyes.', 0),
                ])

        if version < SCHEMA_VERSION:
            db.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')


def get_tasks():
    with connect() as db:
        rows = db.execute('''
            SELECT * FROM tasks
            ORDER BY completed ASC,
                CASE priority
                    WHEN 'High' THEN 0
                    WHEN 'Medium' THEN 1
                    ELSE 2
                END,
                CASE
                    WHEN due_date IS NULL OR due_date = '' THEN 1
                    ELSE 0
                END,
                due_date ASC,
                id DESC
        ''').fetchall()

        return [dict(row) for row in rows]


def get_task_by_id(task_id):
    if not valid_id(task_id):
        return None
    with connect() as db:
        row = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        return dict(row) if row else None


def add_task(title, category, priority, due_date, estimate, notes, operation_id=None):
    """Add a task. Retrying with the same operation_id returns the original task id."""
    category = category if category in CATEGORIES else 'Study'
    priority = priority if priority in PRIORITIES else 'Medium'
    due_date = normalize_date(due_date) or ''

    with connect() as db:
        if operation_id:
            existing = db.execute(
                'SELECT id FROM tasks WHERE operation_id = ?', (operation_id,)
            ).fetchone()
            if existing:
                return existing['id']

        try:
            cursor = db.execute('''
                INSERT INTO tasks
                (title, category, priority, due_date, estimate, notes, operation_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (title, category, priority, due_date, estimate, notes, operation_id))
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Two retries of the same operation raced; the other one won.
            if not operation_id:
                raise
            existing = db.execute(
                'SELECT id FROM tasks WHERE operation_id = ?', (operation_id,)
            ).fetchone()
            if existing:
                return existing['id']
            raise


def update_task_status(task_id, completed):
    if not valid_id(task_id):
        return False
    with connect() as db:
        cursor = db.execute(
            'UPDATE tasks SET completed = ? WHERE id = ?',
            (int(bool(completed)), task_id),
        )
        return cursor.rowcount > 0


def delete_task(task_id):
    """Delete a task. Returns True if a task was actually removed."""
    if not valid_id(task_id):
        return False
    with connect() as db:
        cursor = db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        if cursor.rowcount:
            # Keep focus history, but don't point it at a task that no longer exists.
            db.execute('UPDATE focus_sessions SET task_id = NULL WHERE task_id = ?', (task_id,))
        return cursor.rowcount > 0


def log_focus_session(minutes, task_id=None, session_key=None):
    """Record a finished focus session. Returns False if session_key was already logged."""
    if task_id is not None and not get_task_by_id(task_id):
        task_id = None

    with connect() as db:
        try:
            db.execute('''
                INSERT INTO focus_sessions (task_id, minutes, day, session_key)
                VALUES (?, ?, ?, ?)
            ''', (task_id, minutes, date.today().isoformat(), session_key))
        except sqlite3.IntegrityError:
            if session_key is None:
                raise
            return False
        return True


def focus_summary(day=None):
    day = day or date.today().isoformat()

    with connect() as db:
        row = db.execute('''
            SELECT COUNT(*) AS sessions, COALESCE(SUM(minutes), 0) AS minutes
            FROM focus_sessions
            WHERE day = ?
        ''', (day,)).fetchone()

        return {'sessions': row['sessions'], 'minutes': row['minutes']}


def rescue_plan(available_minutes, trust_dates=True):
    """Create a priority-first plan from unfinished tasks.

    When trust_dates is False (the clock looks unreliable), overdue tasks are
    not promoted ahead of everything else, matching the dashboard, which hides
    overdue labels in that state.
    """
    tasks = [task for task in get_tasks() if not task['completed']]

    today = date.today().isoformat()
    priority_rank = {'High': 0, 'Medium': 1, 'Low': 2}

    def is_overdue(task):
        return trust_dates and bool(task['due_date']) and task['due_date'] < today

    def is_due_today(task):
        return trust_dates and task['due_date'] == today

    tasks.sort(key=lambda task: (
        0 if is_overdue(task) else 1,
        priority_rank.get(task['priority'], 1),
        0 if is_due_today(task) else 1,
        task['due_date'] or '9999-12-31',
        task['estimate'],
    ))

    chosen = []
    deferred = []
    remaining = available_minutes

    for task in tasks:
        task['overdue'] = is_overdue(task)
        if task['estimate'] <= remaining:
            chosen.append(task)
            remaining -= task['estimate']
        else:
            deferred.append(task)

    return {
        'chosen': chosen,
        'deferred': deferred,
        'remaining': remaining,
        'total_planned': available_minutes - remaining,
        'all_count': len(tasks),
        'empty': not tasks,
        'dates_trusted': trust_dates,
    }
