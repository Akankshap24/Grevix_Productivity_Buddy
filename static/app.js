(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const store = {
    get(key, fallback = null, area = localStorage) {
      try { const v = area.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
    },
    set(key, value, area = localStorage) {
      try { area.setItem(key, JSON.stringify(value)); } catch { /* storage may be blocked */ }
    },
    remove(key, area = localStorage) { try { area.removeItem(key); } catch {} },
  };
  const isTyping = el => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

  /* ------------------------------------------------------------------ *
   * Toasts
   * ------------------------------------------------------------------ */
  const toastStack = $('#toastStack');
  function dismissToast(toast) {
    if (!toast || toast.classList.contains('leaving')) return;
    toast.classList.add('leaving');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
  }
  function wireToast(toast, ms = 4500) {
    $('.toast-close', toast)?.addEventListener('click', () => dismissToast(toast));
    let timer = setTimeout(() => dismissToast(toast), ms);
    toast.addEventListener('mouseenter', () => clearTimeout(timer));
    toast.addEventListener('mouseleave', () => { timer = setTimeout(() => dismissToast(toast), 2000); });
  }
  function toast(message, type = 'success', action = null) {
    if (!toastStack) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.setAttribute('role', 'status');
    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    icon.textContent = type === 'error' ? '!' : type === 'info' ? '◷' : '✓';
    const text = document.createElement('span');
    text.textContent = message;
    el.append(icon, text);
    if (action) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'text-button';
      btn.textContent = action.label;
      btn.addEventListener('click', () => { action.run(); dismissToast(el); });
      el.append(btn);
    }
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'toast-close'; close.setAttribute('aria-label', 'Dismiss'); close.textContent = '×';
    el.append(close);
    toastStack.append(el);
    wireToast(el, action ? 9000 : 4500);
  }
  $$('.toast', toastStack || document).forEach(t => wireToast(t));

  /* ------------------------------------------------------------------ *
   * Theme (light / dark) — initial value is set inline in <head>
   * ------------------------------------------------------------------ */
  const root = document.documentElement;
  const themeMeta = $('meta[name="theme-color"]');
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  function applyTheme(theme) {
    root.dataset.theme = theme;
    themeMeta?.setAttribute('content', theme === 'dark' ? '#111119' : '#f7f8fc');
    $$('[data-theme-toggle]').forEach(btn => {
      const next = theme === 'dark' ? 'light' : 'dark';
      btn.setAttribute('aria-label', `Switch to ${next} theme`);
      btn.setAttribute('title', `Switch to ${next} theme (T)`);
    });
  }
  function toggleTheme() {
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('pb-theme', next); } catch {}
    applyTheme(next);
  }
  applyTheme(root.dataset.theme === 'dark' ? 'dark' : 'light');
  $$('[data-theme-toggle]').forEach(btn => btn.addEventListener('click', toggleTheme));
  systemDark.addEventListener?.('change', e => {
    let saved = null;
    try { saved = localStorage.getItem('pb-theme'); } catch {}
    if (!saved) applyTheme(e.matches ? 'dark' : 'light');
  });

  /* ------------------------------------------------------------------ *
   * Greeting
   * ------------------------------------------------------------------ */
  const greeting = $('#greeting');
  if (greeting) {
    const h = new Date().getHours();
    greeting.textContent = h < 5 ? 'WORKING LATE? GO GENTLY' : h < 12 ? 'GOOD MORNING' : h < 17 ? 'GOOD AFTERNOON' : 'GOOD EVENING';
  }

  /* ------------------------------------------------------------------ *
   * Add-task modal (with focus trap)
   * ------------------------------------------------------------------ */
  const modal = $('#taskModal');
  const titleInput = $('#taskTitle');
  let previousFocus = null;
  const modalOpen = () => modal && !modal.hidden;
  function openModal() {
    if (!modal) return;
    previousFocus = document.activeElement;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    setTimeout(() => titleInput?.focus(), 30);
  }
  function closeModal() {
    if (!modal) return;
    modal.hidden = true;
    document.body.style.overflow = '';
    previousFocus?.focus?.();
  }
  ['openTaskModal', 'openTaskModal2', 'emptyAddTask'].forEach(id => document.getElementById(id)?.addEventListener('click', openModal));
  ['closeTaskModal', 'cancelTaskModal'].forEach(id => document.getElementById(id)?.addEventListener('click', closeModal));
  modal?.addEventListener('mousedown', e => { if (e.target === modal) closeModal(); });
  modal?.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    const focusables = $$('input, select, textarea, button', modal).filter(el => !el.disabled && el.offsetParent !== null);
    const first = focusables[0], last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  const dateInput = $('#taskDue');
  if (dateInput) dateInput.min = new Date().toLocaleDateString('en-CA');

  // Confirm deletes without inline JS
  $$('form[data-confirm]').forEach(form => form.addEventListener('submit', e => {
    if (!confirm(form.dataset.confirm)) e.preventDefault();
  }));
  // Give the checkbox a little feedback before the page reloads
  $$('.check-form').forEach(form => form.addEventListener('submit', () => $('.task-check', form)?.classList.add('pop')));

  /* ------------------------------------------------------------------ *
   * Task filters + search (remembered for this tab)
   * ------------------------------------------------------------------ */
  const tabs = $$('.filter-tab');
  const rows = $$('.task-row');
  const search = $('#taskSearch');
  const noResults = $('#noResults');
  const spaces = $$('[data-space]');
  const savedFilter = store.get('pb-filter', { filter: 'all', term: '' }, sessionStorage);
  let activeFilter = savedFilter.filter || 'all';
  if (search) search.value = savedFilter.term || '';

  function filterTasks() {
    const term = (search?.value || '').trim().toLowerCase();
    let visible = 0;
    rows.forEach(row => {
      const show = (activeFilter === 'all' || row.dataset.status === activeFilter) && (row.dataset.search || '').includes(term);
      row.hidden = !show;
      if (show) visible += 1;
    });
    if (noResults) noResults.hidden = visible > 0 || rows.length === 0;
    tabs.forEach(tab => {
      const on = tab.dataset.filter === activeFilter;
      tab.classList.toggle('selected', on);
      tab.setAttribute('aria-pressed', String(on));
    });
    spaces.forEach(s => s.classList.toggle('active', term === s.dataset.space));
    store.set('pb-filter', { filter: activeFilter, term: search?.value || '' }, sessionStorage);
  }
  tabs.forEach(tab => tab.addEventListener('click', () => { activeFilter = tab.dataset.filter; filterTasks(); }));
  search?.addEventListener('input', filterTasks);
  $('#clearFilters')?.addEventListener('click', () => { activeFilter = 'all'; if (search) search.value = ''; filterTasks(); });
  spaces.forEach(space => space.addEventListener('click', () => {
    if (!search) return;
    search.value = search.value.trim().toLowerCase() === space.dataset.space ? '' : space.dataset.space;
    activeFilter = 'all';
    filterTasks();
  }));
  if (rows.length) filterTasks();

  /* ------------------------------------------------------------------ *
   * Sidebar: mobile drawer + active section
   * ------------------------------------------------------------------ */
  const menu = $('#mobileMenu');
  const sidebar = $('#sidebar');
  const scrim = $('#sidebarScrim');
  function setSidebar(open) {
    sidebar?.classList.toggle('open', open);
    if (scrim) scrim.hidden = !open;
    menu?.setAttribute('aria-expanded', String(open));
  }
  menu?.addEventListener('click', () => setSidebar(!sidebar?.classList.contains('open')));
  scrim?.addEventListener('click', () => setSidebar(false));
  window.addEventListener('resize', () => { if (window.innerWidth > 720) setSidebar(false); });

  const navItems = $$('.nav-item[data-section]');
  const crumb = $('#crumbCurrent');
  function setActiveNav(section) {
    navItems.forEach(item => item.classList.toggle('active', item.dataset.section === section));
    const label = navItems.find(i => i.dataset.section === section)?.querySelector('.nav-text')?.textContent;
    if (crumb && label) crumb.textContent = label;
  }
  sidebar?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
    if (link.dataset.section) setActiveNav(link.dataset.section);
    if (link.dataset.space) setActiveNav('tasks');
    setSidebar(false);
  }));
  const sectionFromHash = location.hash.replace('#', '');
  if (navItems.some(i => i.dataset.section === sectionFromHash)) setActiveNav(sectionFromHash);
  let scrollTick = false;
  window.addEventListener('scroll', () => {
    if (scrollTick) return;
    scrollTick = true;
    requestAnimationFrame(() => {
      if (window.scrollY < 80) setActiveNav('overview');
      scrollTick = false;
    });
  }, { passive: true });

  /* ------------------------------------------------------------------ *
   * Rescue form
   * ------------------------------------------------------------------ */
  const rescueForm = $('#rescueForm');
  const rescueInput = $('#availableMinutes');
  const rescueError = $('#rescueError');
  const quickTimes = $$('.quick-times button');
  function syncQuickTimes() { quickTimes.forEach(b => b.classList.toggle('selected', b.dataset.minutes === rescueInput?.value)); }
  quickTimes.forEach(btn => btn.addEventListener('click', () => {
    rescueInput.value = btn.dataset.minutes;
    rescueError.hidden = true;
    rescueInput.closest('.time-input-wrap')?.classList.remove('invalid');
    syncQuickTimes();
  }));
  rescueInput?.addEventListener('input', () => {
    syncQuickTimes();
    rescueError.hidden = true;
    rescueInput.closest('.time-input-wrap')?.classList.remove('invalid');
  });
  syncQuickTimes();
  rescueForm?.addEventListener('submit', e => {
    const value = Number(rescueInput?.value);
    if (!Number.isFinite(value) || value < 15 || value > 720) {
      e.preventDefault();
      rescueError.hidden = false;
      rescueInput.closest('.time-input-wrap')?.classList.add('invalid');
      rescueInput.focus();
    }
  });

  /* ------------------------------------------------------------------ *
   * Focus timer
   * Uses an absolute end timestamp (not a decrementing counter) so it stays
   * accurate in background tabs, and persists in localStorage so it keeps
   * running when the page reloads after completing/adding a task.
   * ------------------------------------------------------------------ */
  const focusCard = $('#focus');
  const timer = (() => {
    if (!focusCard) return null;

    const MODES = {
      focus: { label: 'Focus', min: 5, max: 90, step: 5 },
      short: { label: 'Short break', min: 1, max: 30, step: 1 },
      long: { label: 'Long break', min: 5, max: 45, step: 5 },
    };
    const KEY = 'pb-timer';
    const CIRC = 2 * Math.PI * 88;
    const els = {
      wrap: $('#timerRingWrap'), ring: $('#ringProgress'), display: $('#timerDisplay'), status: $('#timerStatus'),
      start: $('#timerStart'), startLabel: $('#timerStartLabel'), reset: $('#timerReset'), skip: $('#timerSkip'),
      modeTabs: $$('.mode-tab', focusCard), down: $('#durationDown'), up: $('#durationUp'), durLabel: $('#durationLabel'),
      task: $('#focusTask'), dots: $$('#sessionDots span'), today: $('#focusToday'), sound: $('#timerSound'),
      chip: $('#timerChip'), chipText: $('#timerChipText'), navLive: $('#navTimer'),
    };
    els.ring.style.strokeDasharray = CIRC.toFixed(2);
    const baseTitle = document.title;

    const defaults = { mode: 'focus', durations: { focus: 25, short: 5, long: 15 }, running: false, endAt: null, remainingMs: 25 * 60000, cycle: 0, taskId: '', sound: true };
    let state = Object.assign({}, defaults, store.get(KEY, {}));
    state.durations = Object.assign({}, defaults.durations, state.durations);
    if (!MODES[state.mode]) state.mode = 'focus';

    const fullMs = (mode = state.mode) => state.durations[mode] * 60000;
    const remaining = () => state.running ? Math.max(0, state.endAt - Date.now()) : state.remainingMs;
    const isFresh = () => !state.running && state.remainingMs >= fullMs();
    const save = () => store.set(KEY, state);
    const fmt = ms => { const s = Math.ceil(ms / 1000); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };
    const taskTitle = () => {
      const opt = els.task?.selectedOptions[0];
      return opt && opt.value ? opt.textContent.replace(/ · \d+ min$/, '') : '';
    };

    // Drop a linked task that has since been completed or deleted
    if (state.taskId && !$$('option', els.task).some(o => o.value === String(state.taskId))) state.taskId = '';
    if (els.task) els.task.value = state.taskId;

    let focusMinutes = Number(focusCard.dataset.focusMinutes || 0);
    let focusSessions = Number(focusCard.dataset.focusSessions || 0);

    // --- sound -----------------------------------------------------------
    let audioCtx = null;
    function unlockAudio() {
      try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();
      } catch { audioCtx = null; }
    }
    function chime() {
      if (!state.sound) return;
      unlockAudio();
      if (!audioCtx) return;
      const now = audioCtx.currentTime;
      [659.25, 783.99, 1046.5].forEach((freq, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.value = freq;
        const t = now + i * 0.18;
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(0.18, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
        osc.connect(gain).connect(audioCtx.destination);
        osc.start(t);
        osc.stop(t + 1);
      });
    }
    function notify(title, body) {
      if (!('Notification' in window) || Notification.permission !== 'granted' || !document.hidden) return;
      try { new Notification(title, { body, tag: 'pb-timer', icon: $('link[rel="icon"]')?.href }); } catch {}
    }

    // --- render ----------------------------------------------------------
    function render() {
      const left = remaining();
      const total = fullMs();
      const active = state.running || !isFresh();
      const time = fmt(left);

      els.display.textContent = time;
      els.ring.style.strokeDashoffset = (CIRC * (1 - Math.min(1, left / total))).toFixed(2);
      els.wrap.dataset.mode = state.mode;
      els.wrap.classList.toggle('running', state.running);

      els.modeTabs.forEach(tab => {
        const on = tab.dataset.mode === state.mode;
        tab.classList.toggle('selected', on);
        tab.setAttribute('aria-pressed', String(on));
      });

      const t = taskTitle();
      let status;
      if (state.running) status = state.mode === 'focus' ? (t ? `On: ${t}` : 'Deep focus') : 'Breathe. Stretch. Sip water.';
      else if (active) status = 'Paused';
      else status = state.mode === 'focus' ? 'Ready when you are' : state.mode === 'short' ? 'Time for a short breather' : "You've earned a long break";
      els.status.textContent = status;
      els.status.title = status;

      els.start.classList.toggle('running', state.running);
      els.startLabel.textContent = state.running ? 'Pause' : active ? 'Resume' : state.mode === 'focus' ? 'Start focus' : 'Start break';

      const d = state.durations[state.mode];
      els.durLabel.textContent = `${d} min ${state.mode === 'focus' ? 'session' : 'break'}`;
      els.down.disabled = !isFresh() || d <= MODES[state.mode].min;
      els.up.disabled = !isFresh() || d >= MODES[state.mode].max;

      els.dots.forEach((dot, i) => dot.classList.toggle('filled', i < state.cycle));
      if (els.today) els.today.textContent = `${focusMinutes} min focused today${focusSessions ? ` · ${focusSessions} ${focusSessions === 1 ? 'session' : 'sessions'}` : ''}`;
      if (els.sound) {
        els.sound.setAttribute('aria-pressed', String(state.sound));
        els.sound.title = state.sound ? 'Chime is on' : 'Chime is off';
      }

      document.title = active ? `${state.running ? '' : '❚❚ '}${time} · ${MODES[state.mode].label} — Productivity Buddy` : baseTitle;
      if (els.chip) {
        els.chip.hidden = !active;
        els.chip.classList.toggle('paused', !state.running);
        els.chipText.textContent = `${state.mode === 'focus' ? 'Focus' : 'Break'} ${time}`;
      }
      if (els.navLive) { els.navLive.hidden = !active; els.navLive.textContent = time; }
      $$('.task-row').forEach(row => row.classList.toggle('is-focused', active && state.mode === 'focus' && row.dataset.taskId === String(state.taskId)));
    }

    // --- loop ------------------------------------------------------------
    let loop = null;
    function ensureLoop() {
      clearInterval(loop);
      if (!state.running) return;
      loop = setInterval(() => {
        if (remaining() <= 0) complete();
        else render();
      }, 250);
    }

    // --- actions ---------------------------------------------------------
    function start() {
      unlockAudio();
      if ('Notification' in window && Notification.permission === 'default') {
        try { Notification.requestPermission(); } catch {}
      }
      if (state.remainingMs <= 0) state.remainingMs = fullMs();
      state.endAt = Date.now() + state.remainingMs;
      state.running = true;
      save(); render(); ensureLoop();
    }
    function pause() {
      state.remainingMs = remaining();
      state.running = false;
      state.endAt = null;
      save(); render(); ensureLoop();
    }
    function toggle() { state.running ? pause() : start(); }
    function reset() {
      state.running = false; state.endAt = null; state.remainingMs = fullMs();
      save(); render(); ensureLoop();
    }
    function setMode(mode, { silent = false } = {}) {
      if (!MODES[mode] || mode === state.mode && isFresh()) return;
      if (!silent && state.mode === 'focus' && !isFresh() && !confirm('Leave this focus session? Your progress on it won’t be saved.')) return;
      state.mode = mode;
      reset();
    }
    function nextMode(countFocus) {
      if (state.mode === 'focus') {
        if (countFocus) state.cycle = Math.min(4, state.cycle + 1);
        return state.cycle >= 4 ? 'long' : 'short';
      }
      if (state.mode === 'long') state.cycle = 0;
      return 'focus';
    }
    function logSession(minutes, taskId) {
      focusMinutes += minutes;
      focusSessions += 1;
      fetch('/api/focus-sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes, task_id: taskId || null }),
      }).then(r => r.ok ? r.json() : null).then(data => {
        if (data) { focusMinutes = data.minutes; focusSessions = data.sessions; render(); }
      }).catch(() => {});
    }
    function complete() {
      const finished = state.mode;
      const taskId = state.taskId;
      const title = taskTitle();
      if (finished === 'focus') logSession(state.durations.focus, taskId);
      state.mode = nextMode(true);
      state.running = false; state.endAt = null; state.remainingMs = fullMs();
      save(); ensureLoop(); render();

      chime();
      els.wrap.classList.remove('done'); void els.wrap.offsetWidth; els.wrap.classList.add('done');
      if (finished === 'focus') {
        const breakLabel = state.mode === 'long' ? 'a long break' : 'a short break';
        notify('Focus session complete ✳', `Nice work. Time for ${breakLabel}.`);
        const row = taskId && $(`.task-row[data-task-id="${taskId}"]`);
        const checkBtn = row && $('.check-form .task-check:not(.checked)', row);
        toast(`Session done${title ? ` on “${title}”` : ''}. Take ${breakLabel}.`, 'success',
          checkBtn ? { label: 'Mark task done', run: () => checkBtn.closest('form').requestSubmit() } : null);
      } else {
        notify('Break is over', 'Ready for another focus session?');
        toast('Break over — ready when you are.', 'info');
      }
    }
    function skip() {
      if (state.mode === 'focus' && !isFresh() && !confirm('Skip the rest of this focus session? It won’t be counted.')) return;
      state.mode = nextMode(false);
      reset();
    }
    function adjust(dir) {
      if (!isFresh()) return;
      const m = MODES[state.mode];
      state.durations[state.mode] = Math.min(m.max, Math.max(m.min, state.durations[state.mode] + dir * m.step));
      reset();
    }
    function focusOn(taskId) {
      state.taskId = String(taskId || '');
      if (els.task) els.task.value = state.taskId;
      if (state.mode !== 'focus') { state.mode = 'focus'; state.running = false; state.remainingMs = fullMs(); }
      if (!state.running) start(); else { save(); render(); }
      focusCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
      const title = taskTitle();
      if (title) toast(`Focusing on “${title}”. You've got this.`, 'info');
    }

    // --- wiring ----------------------------------------------------------
    els.start.addEventListener('click', toggle);
    els.reset.addEventListener('click', () => {
      if (state.mode === 'focus' && !isFresh() && !confirm('Reset this focus session?')) return;
      reset();
    });
    els.skip.addEventListener('click', skip);
    els.down.addEventListener('click', () => adjust(-1));
    els.up.addEventListener('click', () => adjust(1));
    els.modeTabs.forEach(tab => tab.addEventListener('click', () => setMode(tab.dataset.mode)));
    els.task?.addEventListener('change', () => { state.taskId = els.task.value; save(); render(); });
    els.sound?.addEventListener('click', () => { state.sound = !state.sound; if (state.sound) { unlockAudio(); chime(); } save(); render(); });
    $$('[data-focus-task]').forEach(btn => btn.addEventListener('click', () => focusOn(btn.dataset.focusTask)));
    $$('[data-start-focus]').forEach(link => link.addEventListener('click', () => {
      if (!state.running) { if (state.mode !== 'focus') setMode('focus', { silent: true }); start(); }
    }));

    // Keep multiple open tabs in sync
    window.addEventListener('storage', e => {
      if (e.key !== KEY || !e.newValue) return;
      try { state = Object.assign({}, defaults, JSON.parse(e.newValue)); } catch { return; }
      if (els.task) els.task.value = state.taskId;
      render(); ensureLoop();
    });
    document.addEventListener('visibilitychange', () => { if (!document.hidden) render(); });

    // A session that ended while the page was closed / reloading
    if (state.running && remaining() <= 0) complete();

    // ?focus=<taskId> (from the Rescue plan)
    const params = new URLSearchParams(location.search);
    const fromPlan = params.get('focus');
    if (fromPlan) {
      history.replaceState(null, '', location.pathname + location.hash);
      if ($$('option', els.task).some(o => o.value === fromPlan)) {
        state.taskId = fromPlan;
        els.task.value = fromPlan;
        if (!state.running && state.mode !== 'focus') { state.mode = 'focus'; state.remainingMs = fullMs(); }
        save();
        setTimeout(() => { focusCard.scrollIntoView({ behavior: 'smooth', block: 'center' }); els.start.focus({ preventScroll: true }); }, 150);
        toast(`Ready to focus on “${taskTitle()}”. Press Start when you are.`, 'info');
      }
    }

    render(); ensureLoop();
    return { toggle };
  })();

  /* ------------------------------------------------------------------ *
   * Keyboard shortcuts
   * ------------------------------------------------------------------ */
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (modalOpen()) closeModal();
      else if (sidebar?.classList.contains('open')) setSidebar(false);
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey || modalOpen() || isTyping(e.target)) return;
    const key = e.key.toLowerCase();
    if (key === 'n' && modal) { e.preventDefault(); openModal(); }
    else if (key === '/' && search) { e.preventDefault(); search.focus(); search.select(); }
    else if (key === 't') { toggleTheme(); }
    else if (e.key === ' ' && timer && !/^(BUTTON|A)$/.test(e.target.tagName)) { e.preventDefault(); timer.toggle(); }
  });
})();
