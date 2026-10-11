import math
import os
import secrets
from datetime import date
from urllib.parse import urlsplit

from flask import (Flask, abort, flash, jsonify, make_response, redirect, render_template, request,
                   send_from_directory, session, url_for)

from database import (CATEGORIES, add_task, delete_task, focus_summary, get_task_by_id, get_tasks, init_db,
                      log_focus_session, normalize_date, rescue_plan, update_task_status, valid_id)
from deadline_guard import DeadlineGuard

TITLE_MAX = 120
NOTES_MAX = 300
ESTIMATE_MIN, ESTIMATE_MAX = 5, 600
RESCUE_MIN, RESCUE_MAX, RESCUE_DEFAULT = 15, 720, 120
FOCUS_MIN, FOCUS_MAX = 1, 180
OPERATION_ID_MAX = 100

app = Flask(__name__)
# Use an environment-provided secret in production; a random one is fine for local use.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

deadline_guard = DeadlineGuard()
init_db()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def to_int(value, default=None):
    """Parse an int from form/JSON input without ever raising.

    Accepts "90", 90, 90.0 and "90.5" (rounded). Rejects booleans, NaN and
    infinity (int(float('inf')) raises OverflowError, which used to cause a 500).
    """
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return int(round(number))


def clamp(value, low, high):
    return max(low, min(high, value))


def json_body():
    """Return the request's JSON object, or None if the body isn't a JSON object."""
    data = request.get_json(silent=True)
    if data is None:
        return {}
    return data if isinstance(data, dict) else None


def tasks_anchor():
    """Return to the task list instead of jumping back to the top of the page."""
    return redirect(url_for('index', _anchor='tasks'))


def clock_is_reliable():
    return not deadline_guard.check_clock()['clock_suspicious']


@app.before_request
def block_cross_site_posts():
    """Reject state-changing requests sent from another website (basic CSRF protection).

    Browsers attach an Origin (or at least a Referer) header to cross-site POSTs.
    Requests without either, such as curl or tests, are allowed.
    """
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return None
    if request.headers.get('Sec-Fetch-Site') == 'cross-site':
        abort(403)
    source = request.headers.get('Origin') or request.headers.get('Referer')
    if source and (source == 'null' or urlsplit(source).netloc != request.host):
        abort(403)
    return None


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get('/')
def index():
    tasks = get_tasks()

    clock_status = deadline_guard.check_clock()
    clock_unreliable = clock_status['clock_suspicious']

    today_date = date.today()
    today = today_date.isoformat()

    total = len(tasks)
    completed = sum(1 for task in tasks if task['completed'])
    pending = [task for task in tasks if not task['completed']]

    # Avoid making confident overdue claims when clock reliability is uncertain.
    overdue = 0 if clock_unreliable else sum(
        1 for task in pending if task['due_date'] and task['due_date'] < today
    )

    # Round down so 199 of 200 shows 99%, not a misleading 100%.
    completion_rate = (completed * 100 // total) if total else 0

    # Checked before rendering, because rendering consumes the flashed messages.
    has_flash = bool(session.get('_flashes'))

    response = make_response(render_template(
        'index.html',
        tasks=tasks,
        pending=pending,
        today=today,
        today_label=today_date.strftime('%a, %b %d').replace(' 0', ' '),
        total=total,
        completed=completed,
        pending_count=len(pending),
        overdue=overdue,
        clock_unreliable=clock_unreliable,
        clock_status=clock_status,
        minutes_left=sum(task['estimate'] for task in pending),
        completion_rate=completion_rate,
        category_counts={c: sum(1 for t in pending if t['category'] == c) for c in CATEGORIES},
        focus=focus_summary(today),
    ))
    if has_flash:
        # Tells the service worker not to keep this copy for offline use,
        # so "Task added" toasts aren't replayed later.
        response.headers['X-PB-Offline-Cache'] = 'no'
    return response


@app.get('/sw.js')
def service_worker():
    """Serve the service worker from the site root so it can cache the dashboard for offline use."""
    response = send_from_directory(app.static_folder, 'sw.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.route('/rescue', methods=['GET', 'POST'])
def rescue():
    available = clamp(to_int(request.values.get('available_minutes'), RESCUE_DEFAULT), RESCUE_MIN, RESCUE_MAX)
    if request.method == 'POST':
        # Post/Redirect/Get: refreshing the plan page doesn't re-submit a form.
        return redirect(url_for('rescue', available_minutes=available))
    trusted = clock_is_reliable()
    return render_template('rescue.html', plan=rescue_plan(available, trust_dates=trusted), available=available)


# --------------------------------------------------------------------------- #
# Task forms (used when JavaScript is off)
# --------------------------------------------------------------------------- #
@app.post('/tasks')
def create_task():
    title = request.form.get('title', '').strip()
    if not title:
        flash('Give your task a name first.', 'error')
        return tasks_anchor()

    due_date = normalize_date(request.form.get('due_date', ''))
    if due_date is None:
        flash("That deadline wasn't a valid date, so the task was saved without one.", 'error')
        due_date = ''

    operation_id = request.form.get('operation_id', '').strip()[:OPERATION_ID_MAX] or None

    try:
        add_task(
            title=title[:TITLE_MAX],
            category=request.form.get('category', 'Study'),
            priority=request.form.get('priority', 'Medium'),
            due_date=due_date,
            estimate=clamp(to_int(request.form.get('estimate'), 30), ESTIMATE_MIN, ESTIMATE_MAX),
            notes=request.form.get('notes', '').strip()[:NOTES_MAX],
            operation_id=operation_id,
        )
    except Exception:
        app.logger.exception('Could not create task')
        flash('Task could not be saved. Please try again.', 'error')
        return tasks_anchor()

    flash('Task added to your plan.', 'success')
    return tasks_anchor()


@app.post('/tasks/<int:task_id>/toggle')
def toggle_task(task_id):
    task = get_task_by_id(task_id)
    if task and update_task_status(task_id, not task['completed']):
        flash('Nice work — progress updated.' if not task['completed'] else 'Task moved back to your list.', 'success')
    else:
        flash('That task no longer exists.', 'error')
    return tasks_anchor()


@app.post('/tasks/<int:task_id>/delete')
def remove_task(task_id):
    if delete_task(task_id):
        flash('Task removed.', 'success')
    else:
        flash('That task was already gone.', 'error')
    return tasks_anchor()


# --------------------------------------------------------------------------- #
# JSON API
# --------------------------------------------------------------------------- #
@app.post('/api/tasks/sync')
def sync_task():
    """Create a task from the offline queue. Safe to retry with the same operation_id."""
    data = json_body()
    if data is None:
        return jsonify({'error': 'Request body must be a JSON object'}), 400

    operation_id = data.get('operation_id')
    if not isinstance(operation_id, str) or not operation_id.strip():
        return jsonify({'error': 'operation_id is required'}), 400
    operation_id = operation_id.strip()
    if len(operation_id) > OPERATION_ID_MAX:
        return jsonify({'error': 'operation_id is too long'}), 400

    title = data.get('title')
    if not isinstance(title, str) or not title.strip():
        return jsonify({'error': 'Task title is required'}), 400
    title = title.strip()[:TITLE_MAX]

    due_date = normalize_date(data.get('due_date', ''))
    if due_date is None:
        return jsonify({'error': 'Invalid due date'}), 400

    notes = data.get('notes', '')
    notes = notes.strip()[:NOTES_MAX] if isinstance(notes, str) else ''

    category = data.get('category')
    priority = data.get('priority')

    try:
        task_id = add_task(
            title=title,
            category=category if isinstance(category, str) else 'Study',
            priority=priority if isinstance(priority, str) else 'Medium',
            due_date=due_date,
            estimate=clamp(to_int(data.get('estimate'), 30), ESTIMATE_MIN, ESTIMATE_MAX),
            notes=notes,
            operation_id=operation_id,
        )
    except Exception:
        app.logger.exception('Task synchronization failed')
        return jsonify({'error': 'Task could not be synchronized'}), 500

    task = get_task_by_id(task_id)
    if task is None:
        return jsonify({'error': 'Saved task could not be retrieved'}), 500
    return jsonify({'task': task}), 200


@app.post('/api/focus-sessions')
def record_focus_session():
    data = json_body()
    if data is None:
        return jsonify({'error': 'Request body must be a JSON object'}), 400

    minutes = to_int(data.get('minutes'), 0)
    if not FOCUS_MIN <= minutes <= FOCUS_MAX:
        return jsonify({'error': f'minutes must be between {FOCUS_MIN} and {FOCUS_MAX}'}), 400

    task_id = to_int(data.get('task_id'))
    if not valid_id(task_id):
        task_id = None

    session_key = data.get('session_key')
    session_key = session_key.strip()[:OPERATION_ID_MAX] if isinstance(session_key, str) and session_key.strip() else None

    created = log_focus_session(minutes, task_id, session_key)
    summary = focus_summary()
    summary['duplicate'] = not created
    return jsonify(summary), 201 if created else 200


@app.get('/api/focus-sessions/today')
def focus_today():
    return jsonify(focus_summary())


@app.get('/health')
def health():
    return jsonify({'status': 'ok', 'app': 'Productivity Buddy'})


@app.get('/api/deadline-guard')
def deadline_guard_status():
    return jsonify(deadline_guard.check_clock())


@app.post('/api/deadline-guard/simulate-jump')
def simulate_clock_jump():
    data = json_body()
    if data is None:
        return jsonify({'error': 'Request body must be a JSON object'}), 400

    raw = data.get('jump_seconds', 0)
    if isinstance(raw, bool):
        return jsonify({'error': 'jump_seconds must be a number'}), 400
    try:
        jump_seconds = float(raw)
        return jsonify(deadline_guard.simulate_clock_jump(jump_seconds))
    except (TypeError, ValueError, OverflowError) as error:
        return jsonify({'error': str(error) or 'jump_seconds must be a number'}), 400


@app.post('/api/deadline-guard/reset')
def reset_deadline_guard():
    """Clear a detected or simulated clock jump once the user has checked their clock."""
    return jsonify(deadline_guard.reset())


# Always answer API errors with JSON so the front end never tries to parse an HTML page.
@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(500)
def handle_error(error):
    code = getattr(error, 'code', 500) or 500
    if request.path.startswith('/api/'):
        message = getattr(error, 'description', None) or 'Something went wrong'
        return jsonify({'error': message}), code
    return error if hasattr(error, 'get_response') else ('Internal Server Error', 500)


if __name__ == '__main__':
    # Debug mode (with the interactive debugger) is now opt-in: set FLASK_DEBUG=1 while developing.
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1')
