import os
import secrets
from datetime import date, datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

from database import (CATEGORIES, init_db, get_tasks, add_task, update_task_status, delete_task,
                      get_task_by_id, rescue_plan, log_focus_session, focus_summary)

app = Flask(__name__)
# Use an environment-provided secret in production; a random one is fine for local use.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
init_db()


def tasks_anchor():
    """Return to the task list instead of jumping back to the top of the page."""
    return redirect(url_for('index', _anchor='tasks'))


@app.get('/')
def index():
    tasks = get_tasks()
    today_date = date.today()
    today = today_date.isoformat()
    total = len(tasks)
    completed = sum(1 for task in tasks if task['completed'])
    pending = [task for task in tasks if not task['completed']]
    overdue = sum(1 for task in pending if task['due_date'] and task['due_date'] < today)
    minutes_left = sum(task['estimate'] for task in pending)
    completion_rate = round((completed / total) * 100) if total else 0
    category_counts = {category: sum(1 for task in pending if task['category'] == category) for category in CATEGORIES}
    return render_template('index.html', tasks=tasks, pending=pending, today=today,
                           today_label=today_date.strftime('%a, %b %d').replace(' 0', ' '),
                           total=total, completed=completed, pending_count=len(pending), overdue=overdue,
                           minutes_left=minutes_left, completion_rate=completion_rate,
                           category_counts=category_counts, focus=focus_summary(today))


@app.post('/tasks')
def create_task():
    title = request.form.get('title', '').strip()
    if not title:
        flash('Give your task a name first.', 'error')
        return tasks_anchor()
    due_date = request.form.get('due_date', '').strip()
    if due_date:
        try:
            datetime.strptime(due_date, '%Y-%m-%d')
        except ValueError:
            due_date = ''
    try:
        estimate = max(5, min(600, int(request.form.get('estimate', 30))))
    except (TypeError, ValueError):
        estimate = 30
    add_task(title=title[:120], category=request.form.get('category', 'Study'),
             priority=request.form.get('priority', 'Medium'), due_date=due_date,
             estimate=estimate, notes=request.form.get('notes', '').strip()[:300])
    flash('Task added to your plan.', 'success')
    return tasks_anchor()


@app.post('/tasks/<int:task_id>/toggle')
def toggle_task(task_id):
    task = get_task_by_id(task_id)
    if task:
        update_task_status(task_id, not task['completed'])
        flash('Nice work — progress updated.' if not task['completed'] else 'Task moved back to your list.', 'success')
    else:
        flash('That task no longer exists.', 'error')
    return tasks_anchor()


@app.post('/tasks/<int:task_id>/delete')
def remove_task(task_id):
    delete_task(task_id)
    flash('Task removed.', 'success')
    return tasks_anchor()


@app.route('/rescue', methods=['GET', 'POST'])
def rescue():
    raw = request.values.get('available_minutes', 120)
    try:
        available = max(15, min(720, int(raw)))
    except (TypeError, ValueError):
        available = 120
    if request.method == 'POST':
        # Post/Redirect/Get: refreshing the plan page no longer re-submits a form.
        return redirect(url_for('rescue', available_minutes=available))
    return render_template('rescue.html', plan=rescue_plan(available), available=available)


@app.post('/api/focus-sessions')
def record_focus_session():
    data = request.get_json(silent=True) or {}
    try:
        minutes = int(data.get('minutes', 0))
    except (TypeError, ValueError):
        minutes = 0
    if not 1 <= minutes <= 180:
        return jsonify({'error': 'minutes must be between 1 and 180'}), 400
    task_id = data.get('task_id')
    try:
        task_id = int(task_id) if task_id not in (None, '') else None
    except (TypeError, ValueError):
        task_id = None
    log_focus_session(minutes, task_id)
    return jsonify(focus_summary()), 201


@app.get('/api/focus-sessions/today')
def focus_today():
    return jsonify(focus_summary())


@app.get('/health')
def health():
    return jsonify({'status': 'ok', 'app': 'Productivity Buddy'})


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '1') == '1')
