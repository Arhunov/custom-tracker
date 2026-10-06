/* ПДР Тренер — offline spaced-repetition trainer for the Ukrainian driving-theory exam. */
(function () {
  'use strict';

  const DATA = window.PDR_DATA;
  const RULES = window.PDR_RULES;
  const Q = DATA.questions;
  const BY_ID = new Map(Q.map((q) => [q.id, q]));
  const SECTIONS = DATA.sections;
  const SEC_BY_ID = new Map(SECTIONS.map((s) => [s.id, s]));
  const EXAM_SIZE = 20;
  const EXAM_MAX_ERRORS = 2;
  const EXAM_MINUTES = 20;
  const LEECH_LAPSES = 4;
  const RELEARN_GAP = 4;

  // ---------- persistence ----------
  const store = {
    get(key, fallback) {
      try {
        const v = localStorage.getItem('pdr.' + key);
        return v ? JSON.parse(v) : fallback;
      } catch (e) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem('pdr.' + key, JSON.stringify(value));
      } catch (e) {
        toast('Не вдалося зберегти прогрес');
      }
    },
  };

  const DEFAULT_SETTINGS = { cats: ['B', 'C'], newPerDay: 30, retention: 0.95, shuffle: true, examDate: '', theme: 'auto' };
  let settings = Object.assign({}, DEFAULT_SETTINGS, store.get('settings', {}));
  let cards = store.get('cards', {});   // id -> FSRS state
  let log = store.get('log', {});       // day -> {n, ok, nw}
  const saveCards = () => store.set('cards', cards);
  const saveLog = () => store.set('log', log);
  const saveSettings = () => store.set('settings', settings);

  // ---------- helpers ----------
  function dayIndex(date) {
    const d = date || new Date();
    // the study day rolls over at 04:00 local time
    return Math.floor((d.getTime() - d.getTimezoneOffset() * 60000 - 4 * 3600000) / 86400000);
  }
  const today = () => dayIndex();
  function dayLabel(day) {
    const d = new Date((day * 86400000) + 12 * 3600000);
    return d.getUTCDate() + '.' + String(d.getUTCMonth() + 1).padStart(2, '0');
  }
  function examDay() {
    if (!settings.examDate) return null;
    const [y, m, d] = settings.examDate.split('-').map(Number);
    return Math.floor(Date.UTC(y, m - 1, d) / 86400000);
  }
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = (x) => Math.round(x * 100) + '%';
  function plural(n, one, few, many) {
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }
  const days = (n) => n + ' ' + plural(n, 'день', 'дні', 'днів');
  const ivlLabel = (n) => (n < 30 ? n + ' д' : n < 365 ? Math.round(n / 30) + ' міс' : (n / 365).toFixed(1) + ' р');
  function shuffled(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }
  function toast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.remove('hidden');
    clearTimeout(toast.t);
    toast.t = setTimeout(() => el.classList.add('hidden'), 2200);
  }
  function applyTheme() {
    if (settings.theme === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', settings.theme);
  }

  // ---------- pool & scheduling ----------
  function pool() {
    return Q.filter((q) => q.c.some((c) => settings.cats.includes(c)));
  }
  function inPool(q) {
    return q.c.some((c) => settings.cats.includes(c));
  }
  const recall = (id, day) => FSRS.recallOn(cards[id], day == null ? today() : day);
  const isLeech = (id) => cards[id] && cards[id].lapses >= LEECH_LAPSES;
  function guessProb(q) {
    return 1 / q.a.length;
  }
  function todayLog() {
    const t = today();
    if (!log[t]) log[t] = { n: 0, ok: 0, nw: 0 };
    return log[t];
  }
  function dueCards(list) {
    const t = today();
    return list.filter((q) => cards[q.id] && cards[q.id].due <= t)
      .sort((a, b) => recall(a.id) - recall(b.id));
  }
  function newCards(list) {
    return list.filter((q) => !cards[q.id]);
  }
  function newLeftToday() {
    return Math.max(0, settings.newPerDay - (log[today()] ? log[today()].nw : 0));
  }
  function readiness(day) {
    const p = pool();
    const probs = p.map((q) => (cards[q.id] ? FSRS.recallOn(cards[q.id], day) : guessProb(q)));
    const mean = probs.reduce((a, b) => a + b, 0) / (probs.length || 1);
    return { pass: FSRS.passProbability(probs, EXAM_SIZE, EXAM_MAX_ERRORS), mean };
  }
  function interleave(reviews, fresh) {
    // one new card after every 3 reviews, the rest of the new ones at the end
    const out = [];
    let r = 0, n = 0;
    while (r < reviews.length || n < fresh.length) {
      for (let k = 0; k < 3 && r < reviews.length; k++) out.push(reviews[r++]);
      if (n < fresh.length) out.push(fresh[n++]);
    }
    return out;
  }
  function grade(id, g) {
    const t = today();
    const wasNew = !cards[id];
    cards[id] = FSRS.review(cards[id], g, t, { retention: settings.retention, fuzz: Math.random() });
    const l = todayLog();
    l.n++;
    if (g > 1) l.ok++;
    if (wasNew) l.nw++;
    saveCards();
    saveLog();
  }

  // ---------- navigation ----------
  const stack = [];
  let view = null;
  let timerHandle = null;
  function go(name, params, replace) {
    if (view && !replace) stack.push(view);
    view = { name, params: params || {} };
    render();
    window.scrollTo(0, 0);
  }
  function back() {
    if (!document.getElementById('modal').classList.contains('hidden')) {
      closeModal();
      return true;
    }
    if (view && view.name === 'exam' && !view.params.state.finished) {
      if (!confirm('Завершити іспит? Результат буде зараховано.')) return true;
      finishExam(view.params.state);
      return true;
    }
    if (!stack.length) return false;
    view = stack.pop();
    render();
    return true;
  }
  window.handleBack = back;

  function render() {
    clearInterval(timerHandle);
    const app = document.getElementById('app');
    const fn = SCREENS[view.name];
    app.innerHTML = fn(view.params);
    const bb = document.querySelector('.bottombar');
    app.style.paddingBottom = bb ? (bb.offsetHeight + 24) + 'px' : '';
    if (view.name === 'exam') startExamTimer(view.params.state);
  }
  function topbar(title, opts) {
    const left = stack.length ? '<button class="iconbtn" data-act="back" aria-label="Назад">←</button>' : '';
    return `<div class="topbar">${left}<h1>${esc(title)}</h1>${(opts && opts.right) || ''}</div>`;
  }

  // ---------- modal ----------
  function openModal(html, cls) {
    const m = document.getElementById('modal');
    m.innerHTML = `<div class="sheet ${cls || ''}">${html}</div>`;
    m.classList.remove('hidden');
  }
  function closeModal() {
    const m = document.getElementById('modal');
    m.classList.add('hidden');
    m.innerHTML = '';
  }

  // ---------- rules lookup ----------
  const RULE_SEC = new Map(RULES.sections.map((s) => [s.num, s]));
  function numInHead(head, num) {
    // head like "1.3.1, 1.3.2", "5.31.1-5.31.3", "5.21.1 і 5.21.2", "1.1"
    const parts = head.split(/\s*(?:,|\sі\s)\s*/);
    for (const p of parts) {
      const range = p.split(/\s*[-–—]\s*/);
      if (range.length === 2) {
        const a = range[0].split('.'), b = range[1].split('.'), n = num.split('.');
        if (a.length === n.length && b.length === n.length &&
            a.slice(0, -1).join('.') === n.slice(0, -1).join('.') &&
            +n[n.length - 1] >= +a[a.length - 1] && +n[n.length - 1] <= +b[b.length - 1]) return true;
      } else if (p.trim() === num) return true;
    }
    return false;
  }
  function findRule(ref, context) {
    const m = ref.match(/(п\.|пункт|знак|знаки|розмітка|розмітки|табличка|таблички|розділ)?\s*(\d+(?:\.\d+)*)/i);
    if (!m) return null;
    let kind = (m[1] || 'п.').toLowerCase();
    const num = m[2];
    let sec, lines, start = -1;
    if (kind === 'розділ' || (kind === 'п.' && !num.includes('.'))) {
      sec = RULE_SEC.get(num);
      if (!sec) return null;
      return { sec, text: sec.text.length > 1500 ? sec.text.slice(0, 1500) + '…' : sec.text, num, title: 'Розділ ' + num };
    }
    if (kind.startsWith('табличк')) kind = 'знак';
    if (kind.startsWith('знак') || kind.startsWith('розміт')) {
      sec = RULE_SEC.get(kind.startsWith('знак') ? '33' : '34');
      lines = sec.text.split('\n');
      for (let i = 0; i < lines.length; i++) {
        const h = lines[i].match(/^(\d+(?:\.\d+)+(?:\s*(?:,|\sі\s|[-–—])\s*\d+(?:\.\d+)+)*)/);
        if (h && numInHead(h[1], num)) { start = i; break; }
      }
      if (start < 0) return { sec, text: null, num };
      let end = start + 1;
      while (end < lines.length && !/^\d+(\.\d+)+[\s“"(,-]/.test(lines[end]) && !/^\d+\. /.test(lines[end])) end++;
      return { sec, text: lines.slice(start, end).join('\n'), num, title: (kind.startsWith('знак') ? 'Знак ' : 'Розмітка ') + num };
    }
    const top = num.split('.')[0];
    sec = RULE_SEC.get(top);
    if (!sec) return null;
    lines = sec.text.split('\n');
    const re = new RegExp('^' + num.replace(/\./g, '\\.') + '\\.?\\s');
    start = lines.findIndex((l) => re.test(l));
    if (start < 0) return { sec, text: null, num };
    let end = start + 1;
    while (end < lines.length && !/^\d+\.\d+\.?\s/.test(lines[end])) end++;
    let text = lines.slice(start, end).join('\n');
    const term = ref.match(/[«"“]([^»"”]+)[»"”]/);
    if (num === '1.10') {
      // the glossary is huge: show only the terms relevant to the question
      const block = lines.slice(start + 1, end);
      const ctxText = ((term ? term[1] : '') + ' ' + (context || '')).toLowerCase();
      const stem = (w) => w.slice(0, Math.max(4, w.length - 2));
      const hits = block.filter((l) => {
        const m2 = l.match(/^([^-–—]{3,60}?)\s+[-–—]\s/);
        if (!m2) return false;
        const words = m2[1].toLowerCase().replace(/\(.*?\)/g, ' ').split(/[^а-яіїєґ']+/).filter((w) => w.length > 2);
        return words.length > 0 && words.every((w) => ctxText.includes(stem(w)));
      });
      if (hits.length) return { sec, text: hits.join('\n'), num, title: 'Пункт 1.10 · терміни', full: true };
    }
    return { sec, text, num, title: 'Пункт ' + num };
  }
  function showRule(ref, qid) {
    const q = qid && BY_ID.get(qid);
    const r = findRule(ref, q ? [q.t, q.a.join(' '), q.e || ''].join(' ') : '');
    if (!r) { toast('Пункт не знайдено'); return; }
    const body = r.text ? `<div class="ruletext">${esc(r.text)}</div>` : '<p class="muted">Точний пункт не знайдено — відкрийте розділ.</p>';
    openModal(`<div class="row"><h2 style="margin:0;flex:1">${esc(r.title || ref)}</h2><button class="iconbtn" data-act="close">✕</button></div>
      <p class="muted small">Розділ ${esc(r.sec.num)}. ${esc(r.sec.title)}</p>${body}
      <p><button class="btn" data-act="open-pdr" data-sec="${esc(r.sec.num)}" data-num="${esc(r.num)}">Відкрити розділ ПДР</button></p>`);
  }

  // ---------- question rendering ----------
  function questionHTML(q, order, chosen, revealed, opts) {
    const img = q.img ? `<img class="qimg" src="img/${q.img}.webp" alt="" data-act="zoom" data-img="${q.img}">` : '';
    const ans = order.map((orig, i) => {
      let cls = 'ans';
      if (revealed) {
        if (orig === q.k) cls += ' correct';
        else if (orig === chosen) cls += ' wrong';
      } else if (orig === chosen) cls += ' sel';
      return `<button class="${cls}" data-act="answer" data-i="${orig}"><span class="n">${i + 1}.</span><span>${esc(q.a[orig])}</span></button>`;
    }).join('');
    let ex = '';
    if (revealed && !(opts && opts.hideExplain)) ex = explainHTML(q, order, chosen);
    return `${img}<p class="qtext">${esc(q.t)}</p><div class="answers ${revealed ? 'locked' : ''}">${ans}</div>${ex}`;
  }
  function explainHTML(q, order, chosen) {
    const right = chosen === q.k;
    const pos = order.indexOf(q.k) + 1;
    const verdict = chosen == null ? '' : right
      ? '<div class="verdict ok">✓ Правильно</div>'
      : `<div class="verdict bad">✗ Неправильно — правильна відповідь ${pos}</div>`;
    const rules = (q.r || []).map((r) => (/КУпАП|Кодекс|Закон/i.test(r)
      ? `<span class="rule static">${esc(r)}</span>`
      : `<button class="rule" data-act="rule" data-ref="${esc(r)}" data-q="${esc(q.id)}">${esc(r)}</button>`)).join('');
    return `<div class="card explain">${verdict}
      ${q.e ? `<div>${esc(q.e)}</div>` : '<div class="muted">Пояснення ще немає.</div>'}
      ${q.tip ? `<div class="tip">💡 ${esc(q.tip)}</div>` : ''}
      ${rules ? `<div class="rules">${rules}</div>` : ''}
      ${q.flag ? `<div class="flag">⚠️ ${esc(q.flag)}</div>` : ''}
    </div>`;
  }
  function answerOrder(q) {
    const idx = q.a.map((_, i) => i);
    return settings.shuffle && !q.fx ? shuffled(idx) : idx;
  }
  function cardBadge(id) {
    const c = cards[id];
    if (isLeech(id)) return '<span class="badge leech">складне</span>';
    if (!c) return '<span class="badge new">нове</span>';
    return '';
  }

  // ---------- study session ----------
  function startSession(kind, ids, title) {
    if (!ids.length) { toast('Немає питань для цього режиму'); return; }
    const s = { kind, title, queue: ids.slice(), pos: 0, done: new Set(), relearn: new Set(), answered: 0, correct: 0, cur: null };
    nextCard(s);
    go('study', { s });
  }
  function nextCard(s) {
    if (s.pos >= s.queue.length) { s.cur = null; return; }
    const id = s.queue[s.pos];
    s.cur = { id, order: answerOrder(BY_ID.get(id)), chosen: null, re: s.done.has(id) };
  }
  function requeue(s, id) {
    const at = Math.min(s.queue.length, s.pos + 1 + RELEARN_GAP);
    s.queue.splice(at, 0, id);
    s.relearn.add(id);
  }
  function studyScreen({ s }) {
    if (!s.cur) {
      const acc = s.answered ? Math.round(100 * s.correct / s.answered) : 0;
      return topbar(s.title) + `<div class="card hero"><div class="big">🎉</div><h2>Сесію завершено</h2>
        <p class="muted">Відповідей: ${s.answered} · правильно з першої спроби: ${acc}%</p></div>
        <button class="btn primary" data-act="home">На головну</button>`;
    }
    const q = BY_ID.get(s.cur.id);
    const left = s.queue.length - s.pos;
    const isRe = s.cur.re;
    const badge = isRe ? '<span class="badge again">ще раз</span>' : cardBadge(q.id);
    const revealed = s.cur.chosen != null;
    let bar = '';
    if (revealed) {
      const right = s.cur.chosen === q.k;
      if (!right || isRe) {
        bar = '<button class="btn primary" data-act="next">Далі</button>';
      } else {
        const pv = FSRS.preview(cards[q.id], today(), { retention: settings.retention });
        bar = `<button class="btn" data-act="grade" data-g="1">Вгадав<span class="sub">завтра</span></button>
          <button class="btn ok" data-act="grade" data-g="3">Знав<span class="sub">${ivlLabel(pv[3])}</span></button>
          <button class="btn" data-act="grade" data-g="4">Легко<span class="sub">${ivlLabel(pv[4])}</span></button>`;
      }
    }
    return topbar(s.title, { right: `<span class="muted small">${left} залиш.</span>` }) +
      `<div class="q-meta"><span>№ ${esc(q.id)} · ${esc(SEC_BY_ID.get(q.s).title)}</span>${badge}</div>` +
      questionHTML(q, s.cur.order, s.cur.chosen, revealed) +
      (bar ? `<div class="bottombar"><div class="inner">${bar}</div></div>` : '');
  }
  function studyAnswer(s, i) {
    if (s.cur.chosen != null) return;
    s.cur.chosen = i;
    const q = BY_ID.get(s.cur.id);
    const right = i === q.k;
    const first = !s.done.has(q.id);
    if (first) {
      s.answered++;
      if (right) s.correct++;
      else {
        grade(q.id, 1);
        s.done.add(q.id);
        requeue(s, q.id);
      }
    } else if (!right) {
      requeue(s, q.id);
    }
    render();
    const ex = document.querySelector('.explain');
    if (ex) ex.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  function studyGrade(s, g) {
    const id = s.cur.id;
    grade(id, g);
    s.done.add(id);
    if (g === 1) requeue(s, id);
    s.pos++;
    nextCard(s);
    render();
    window.scrollTo(0, 0);
  }
  function studyNext(s) {
    s.pos++;
    nextCard(s);
    render();
    window.scrollTo(0, 0);
  }

  // ---------- exam ----------
  function startExam() {
    const ids = shuffled(pool().map((q) => q.id)).slice(0, EXAM_SIZE);
    const state = { ids, orders: ids.map((id) => answerOrder(BY_ID.get(id))), answers: ids.map(() => null), cur: 0,
      endsAt: Date.now() + EXAM_MINUTES * 60000, started: Date.now(), finished: false, review: null };
    go('exam', { state });
  }
  function examErrors(st) {
    return st.ids.reduce((n, id, i) => n + (st.answers[i] != null && st.answers[i] !== BY_ID.get(id).k ? 1 : 0), 0);
  }
  function examScreen({ state: st }) {
    if (st.finished) return examResult(st);
    const q = BY_ID.get(st.ids[st.cur]);
    const dots = st.ids.map((id, i) => {
      const a = st.answers[i];
      const cls = a == null ? '' : a === BY_ID.get(id).k ? 'okd' : 'badd';
      return `<button class="dot ${cls} ${i === st.cur ? 'cur' : ''}" data-act="exam-go" data-i="${i}">${i + 1}</button>`;
    }).join('');
    const chosen = st.answers[st.cur];
    const answered = chosen != null;
    let feedback = '';
    let bar = '<button class="btn" data-act="exam-skip">Пропустити</button><button class="btn primary" data-act="exam-finish">Завершити</button>';
    if (answered) {
      // like the official exam: show right away whether the answer was correct
      const right = chosen === q.k;
      const errors = examErrors(st);
      feedback = `<div class="card explain"><div class="verdict ${right ? 'ok' : 'bad'}">${right ? '✓ Правильно' : '✗ Неправильно — правильна відповідь ' + (st.orders[st.cur].indexOf(q.k) + 1)}</div>
        <div class="muted small">Помилок: ${errors} (можна ${EXAM_MAX_ERRORS})${errors > EXAM_MAX_ERRORS ? ' — іспит уже не складено' : ''}</div>
        ${q.e ? `<details style="margin-top:8px"><summary class="small">Пояснення</summary>${explainHTML(q, st.orders[st.cur], null)}</details>` : ''}</div>`;
      const last = nextUnanswered(st, st.cur) < 0;
      bar = last
        ? '<button class="btn primary" data-act="exam-finish">Результат</button>'
        : '<button class="btn" data-act="exam-finish">Завершити</button><button class="btn primary" data-act="exam-next">Далі</button>';
    }
    return topbar('Іспит', { right: '<span class="timer" id="timer"></span>' }) +
      `<div class="dots">${dots}</div>` +
      `<div class="q-meta"><span>Питання ${st.cur + 1} з ${EXAM_SIZE}</span><span>№ ${esc(q.id)}</span></div>` +
      questionHTML(q, st.orders[st.cur], chosen, answered, { hideExplain: true }) + feedback +
      `<div class="bottombar"><div class="inner">${bar}</div></div>`;
  }
  function startExamTimer(st) {
    if (st.finished) return;
    const tick = () => {
      const left = Math.max(0, st.endsAt - Date.now());
      const el = document.getElementById('timer');
      if (el) el.textContent = Math.floor(left / 60000) + ':' + String(Math.floor(left / 1000) % 60).padStart(2, '0');
      if (left <= 0) finishExam(st);
    };
    tick();
    timerHandle = setInterval(tick, 500);
  }
  function examAnswer(st, i) {
    if (st.answers[st.cur] != null) return; // answers are final, as in the official exam
    st.answers[st.cur] = i;
    render();
    const fb = document.querySelector('.explain');
    if (fb) fb.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  function examNext(st) {
    const nextIdx = nextUnanswered(st, st.cur);
    if (nextIdx < 0) { finishExam(st); return; }
    st.cur = nextIdx;
    render();
    window.scrollTo(0, 0);
  }
  function nextUnanswered(st, from) {
    for (let k = 1; k <= EXAM_SIZE; k++) {
      const i = (from + k) % EXAM_SIZE;
      if (st.answers[i] == null) return i;
    }
    return -1;
  }
  function finishExam(st) {
    if (st.finished) return;
    st.finished = true;
    st.took = Math.round((Date.now() - st.started) / 1000);
    // feed results into the scheduler: errors are lapses, correct answers count only for cards already being learned
    st.ids.forEach((id, i) => {
      const a = st.answers[i];
      if (a != null && a !== BY_ID.get(id).k) grade(id, 1);
      else if (a === BY_ID.get(id).k && cards[id]) grade(id, 3);
    });
    const hist = store.get('exams', []);
    hist.push({ day: today(), errors: examErrors(st) + st.answers.filter((a) => a == null).length, took: st.took });
    store.set('exams', hist.slice(-100));
    render();
    window.scrollTo(0, 0);
  }
  function examResult(st) {
    const unanswered = st.answers.filter((a) => a == null).length;
    const errors = examErrors(st) + unanswered;
    const passed = errors <= EXAM_MAX_ERRORS;
    if (st.review != null) {
      const i = st.review;
      const q = BY_ID.get(st.ids[i]);
      return topbar(`Питання ${i + 1} з ${EXAM_SIZE}`) +
        `<div class="q-meta"><span>№ ${esc(q.id)} · ${esc(SEC_BY_ID.get(q.s).title)}</span></div>` +
        questionHTML(q, st.orders[i], st.answers[i], true) +
        `<div class="bottombar"><div class="inner"><button class="btn" data-act="exam-review" data-i="${i - 1}" ${i === 0 ? 'disabled' : ''}>←</button>
        <button class="btn primary" data-act="exam-review" data-i="-1">До результатів</button>
        <button class="btn" data-act="exam-review" data-i="${i + 1}" ${i === EXAM_SIZE - 1 ? 'disabled' : ''}>→</button></div></div>`;
    }
    const dots = st.ids.map((id, i) => {
      const ok = st.answers[i] === BY_ID.get(id).k;
      return `<button class="dot ${ok ? 'okd' : 'badd'}" data-act="exam-review" data-i="${i}">${i + 1}</button>`;
    }).join('');
    const mm = Math.floor(st.took / 60), ss = String(st.took % 60).padStart(2, '0');
    return topbar('Результат іспиту') +
      `<div class="card hero"><div class="big" style="color:var(${passed ? '--ok' : '--bad'})">${passed ? 'Склав' : 'Не склав'}</div>
      <p class="muted">Помилок: ${errors} з ${EXAM_SIZE} (дозволено ${EXAM_MAX_ERRORS})${unanswered ? ` · без відповіді: ${unanswered}` : ''} · час ${mm}:${ss}</p></div>
      <p class="muted small">Натисніть номер, щоб переглянути питання з поясненням. Помилки автоматично додано до повторення на завтра.</p>
      <div class="dots">${dots}</div>
      <div class="bottombar"><div class="inner"><button class="btn" data-act="home">На головну</button><button class="btn primary" data-act="exam-again">Ще іспит</button></div></div>`;
  }

  // ---------- screens ----------
  const SCREENS = {
    home() {
      const p = pool();
      const due = dueCards(p).length;
      const fresh = Math.min(newLeftToday(), newCards(p).length);
      const learned = p.filter((q) => cards[q.id]).length;
      const r = readiness(today());
      const leeches = p.filter((q) => isLeech(q.id)).length;
      const ed = examDay();
      let examLine = '';
      if (ed != null && ed >= today()) {
        const left = ed - today();
        const remainingNew = newCards(p).length;
        const perDay = Math.ceil(remainingNew / Math.max(1, left - 3));
        const rEx = readiness(ed);
        examLine = `<p class="small" style="margin:10px 0 0">📅 До іспиту ${days(left)} · прогноз на день іспиту: <b>${pct(rEx.pass)}</b>` +
          (remainingNew ? ` · щоб встигнути, вчіть ≈${perDay} нових/день` : '') + '</p>';
      }
      const cats = [['B', 'B · легковий'], ['C', 'C · вантажний']].map(([c, l]) =>
        `<button class="chip ${settings.cats.includes(c) ? 'on' : ''}" data-act="cat" data-c="${c}">${l}</button>`).join('');
      const studyBtn = due + fresh > 0
        ? `<button class="btn primary" data-act="study">Вчити<span class="sub">${due} на повторення · ${fresh} нових</span></button>`
        : `<button class="btn" data-act="study-more">На сьогодні все ✓<span class="sub">Взяти ще 10 нових</span></button>`;
      return `<div class="topbar"><h1>ПДР Тренер</h1><button class="iconbtn" data-act="go" data-to="settings" aria-label="Налаштування">⚙</button></div>
        <div class="chips" style="margin-bottom:12px">${cats}</div>
        <div class="card hero">
          <div class="muted small">Шанс скласти іспит сьогодні</div>
          <div class="big">${pct(r.pass)}</div>
          <div class="muted small">середнє запам'ятовування ${pct(r.mean)} · вивчено ${learned} з ${p.length}</div>
          <div class="bar ok" style="margin-top:10px"><i style="width:${(100 * learned / (p.length || 1)).toFixed(1)}%"></i></div>
          ${examLine}
        </div>
        ${studyBtn}
        <div class="grid" style="margin-top:12px">
          <button class="tile" data-act="exam"><b>🎯 Іспит</b><span>${EXAM_SIZE} питань · ${EXAM_MINUTES} хв</span></button>
          <button class="tile" data-act="go" data-to="sections"><b>📚 Розділи</b><span>вчити по темах</span></button>
          <button class="tile" data-act="weak"><b>🔥 Найслабші</b><span>що забуваєте найшвидше</span></button>
          <button class="tile" data-act="go" data-to="hard"><b>🧠 Складні</b><span>${leeches} ${plural(leeches, 'питання', 'питання', 'питань')} з частими помилками</span></button>
          <button class="tile" data-act="go" data-to="browse"><b>🔍 Пошук</b><span>усі питання з відповідями</span></button>
          <button class="tile" data-act="go" data-to="pdr"><b>📖 ПДР</b><span>текст правил</span></button>
          <button class="tile" data-act="go" data-to="stats"><b>📊 Статистика</b><span>прогрес і прогноз</span></button>
          <button class="tile" data-act="go" data-to="help"><b>❓ Як вчити</b><span>метод і поради</span></button>
        </div>`;
    },
    study: studyScreen,
    exam: examScreen,
    sections() {
      const t = today();
      const items = SECTIONS.filter((s) => s.categories.some((c) => settings.cats.includes(c))).map((s) => {
        const qs = Q.filter((q) => q.s === s.id);
        const learned = qs.filter((q) => cards[q.id]).length;
        const due = qs.filter((q) => cards[q.id] && cards[q.id].due <= t).length;
        const mean = learned ? qs.reduce((a, q) => a + recall(q.id), 0) / qs.length : 0;
        return `<button class="item" data-act="go" data-to="section" data-id="${esc(s.id)}">
          <div class="t">${esc(s.id)}. ${esc(s.title)}</div>
          <div class="muted small">${learned}/${qs.length} вивчено${due ? ` · ${due} на повторення` : ''} · пам'ять ${pct(mean)}</div>
          <div class="bar" style="margin-top:6px"><i style="width:${(100 * learned / qs.length).toFixed(1)}%"></i></div></button>`;
      }).join('');
      return topbar('Розділи') + `<div class="list">${items}</div>`;
    },
    section({ id }) {
      const s = SEC_BY_ID.get(id);
      const qs = Q.filter((q) => q.s === id);
      const due = dueCards(qs).length;
      const fresh = newCards(qs).length;
      return topbar(`${s.id}. ${s.title}`) +
        `<div class="card"><p style="margin-top:0">${qs.length} питань · ${fresh} нових · ${due} на повторення</p>
        <div class="list">
          <button class="btn primary" data-act="sec-study" data-id="${esc(id)}">Вчити розділ<span class="sub">повторення + до 20 нових</span></button>
          <button class="btn" data-act="sec-all" data-id="${esc(id)}">Прогнати всі питання розділу<span class="sub">у випадковому порядку</span></button>
          <button class="btn" data-act="go" data-to="browse" data-sec="${esc(id)}">Переглянути з відповідями</button>
        </div></div>`;
    },
    hard() {
      const p = pool().filter((q) => cards[q.id] && cards[q.id].lapses > 0)
        .sort((a, b) => cards[b.id].lapses - cards[a.id].lapses || recall(a.id) - recall(b.id));
      const rows = p.slice(0, 100).map((q) => `<div class="qrow"><div class="small muted">№ ${esc(q.id)} · помилок: ${cards[q.id].lapses} ${isLeech(q.id) ? '<span class="badge leech">складне</span>' : ''}</div>
        <div>${esc(q.t)}</div><div class="ok small">→ ${esc(q.a[q.k])}</div></div>`).join('');
      return topbar('Складні питання') +
        (p.length ? `<button class="btn primary" data-act="hard-drill" style="margin-bottom:12px">Тренувати ${Math.min(30, p.length)} найскладніших</button><div class="list">${rows}</div>`
          : '<div class="empty">Поки немає питань з помилками. Так тримати!</div>');
    },
    browse({ sec, query, limit }) {
      limit = limit || 40;
      let list = sec ? Q.filter((q) => q.s === sec) : pool();
      const qq = (query || '').trim().toLowerCase();
      if (qq) list = list.filter((q) => q.id === qq || q.t.toLowerCase().includes(qq) || q.a.some((a) => a.toLowerCase().includes(qq)));
      const rows = list.slice(0, limit).map((q) => `<details class="qrow"><summary><span class="muted small">№ ${esc(q.id)}</span> ${esc(q.t)}
        <div class="ok small">→ ${esc(q.a[q.k])}</div></summary>
        ${q.img ? `<img class="qimg" style="margin-top:10px" loading="lazy" src="img/${q.img}.webp" alt="" data-act="zoom" data-img="${q.img}">` : ''}
        ${explainHTML(q, q.a.map((_, i) => i), null)}</details>`).join('');
      const title = sec ? `${sec}. ${SEC_BY_ID.get(sec).title}` : 'Усі питання';
      return topbar(title) +
        `<input type="search" id="search" placeholder="Пошук за текстом або номером" value="${esc(query || '')}" style="margin-bottom:12px">
        <p class="muted small">Знайдено: ${list.length}</p><div class="list">${rows}</div>` +
        (list.length > limit ? `<p><button class="btn" data-act="more">Показати ще</button></p>` : '');
    },
    pdr({ sec, num }) {
      if (!sec) {
        const items = RULES.sections.map((s) => `<button class="item" data-act="go" data-to="pdr" data-sec="${esc(s.num)}"><span class="t">${esc(s.num)}. ${esc(s.title)}</span></button>`).join('');
        return topbar('Правила дорожнього руху') + `<p class="muted small">Редакція з zakon.rada.gov.ua</p><div class="list">${items}</div>`;
      }
      const s = RULE_SEC.get(sec);
      const lines = s.text.split('\n').map((l, i) => `<div class="pdr-line" id="l${i}">${esc(l)}</div>`).join('');
      return topbar(`${s.num}. ${s.title}`) + `<div class="card ruletext" style="white-space:normal">${lines}</div>`;
    },
    stats() {
      const p = pool();
      const t = today();
      const buckets = { nw: 0, l: 0, y: 0, m: 0 };
      p.forEach((q) => {
        const c = cards[q.id];
        if (!c) buckets.nw++;
        else if (c.s < 7) buckets.l++;
        else if (c.s < 30) buckets.y++;
        else buckets.m++;
      });
      const r = readiness(t);
      const tl = log[t] || { n: 0, ok: 0, nw: 0 };
      let streak = 0;
      for (let d = log[t] && log[t].n ? t : t - 1; log[d] && log[d].n; d--) streak++;
      let n7 = 0, ok7 = 0;
      for (let d = t - 6; d <= t; d++) if (log[d]) { n7 += log[d].n; ok7 += log[d].ok; }
      const fc = [];
      for (let d = 0; d < 14; d++) fc.push(p.filter((q) => cards[q.id] && (d === 0 ? cards[q.id].due <= t : cards[q.id].due === t + d)).length);
      const hist = [];
      for (let d = t - 29; d <= t; d++) hist.push(log[d] ? log[d].n : 0);
      const chart = (vals, labelFn) => {
        const max = Math.max(1, ...vals);
        return `<div class="chart">${vals.map((v, i) => `<div class="col"><em>${v || ''}</em><i style="height:${(80 * v / max).toFixed(1)}%"></i><small>${labelFn(i)}</small></div>`).join('')}</div>`;
      };
      const exams = store.get('exams', []);
      const lastEx = exams.slice(-10);
      const passed = lastEx.filter((e) => e.errors <= EXAM_MAX_ERRORS).length;
      return topbar('Статистика') +
        `<div class="stats">
          <div class="stat"><b>${pct(r.pass)}</b><span>шанс скласти іспит</span></div>
          <div class="stat"><b>${pct(r.mean)}</b><span>середнє запам'ятовування</span></div>
          <div class="stat"><b>${tl.n}</b><span>відповідей сьогодні (${tl.nw} нових)</span></div>
          <div class="stat"><b>${n7 ? pct(ok7 / n7) : '—'}</b><span>точність за 7 днів</span></div>
          <div class="stat"><b>${days(streak)}</b><span>поспіль без пропусків</span></div>
          <div class="stat"><b>${lastEx.length ? passed + '/' + lastEx.length : '—'}</b><span>останні іспити складено</span></div>
        </div>
        <h2>Стан питань (${p.length})</h2>
        <div class="card">
          ${[['Нові', buckets.nw, 'var(--line)'], ['Вивчаються (< тижня пам\'яті)', buckets.l, 'var(--bad)'], ['Закріплюються (1–4 тижні)', buckets.y, 'var(--warn)'], ['Вивчені в усмерть (> місяця)', buckets.m, 'var(--ok)']]
            .map(([l, v, c]) => `<div class="row small" style="margin:4px 0"><span style="width:10px;height:10px;border-radius:3px;background:${c};display:inline-block"></span><span class="spacer">${l}</span><b>${v}</b></div>`).join('')}
          <div class="bar" style="display:flex;margin-top:8px">${[['m', 'var(--ok)'], ['y', 'var(--warn)'], ['l', 'var(--bad)']].map(([k, c]) => `<i style="width:${(100 * buckets[k] / (p.length || 1)).toFixed(2)}%;background:${c};border-radius:0"></i>`).join('')}</div>
        </div>
        <h2>Прогноз повторень на 14 днів</h2>
        <div class="card">${chart(fc, (i) => (i === 0 ? 'сьог' : i % 2 === 0 ? dayLabel(t + i) : ''))}</div>
        <h2>Активність за 30 днів</h2>
        <div class="card">${chart(hist, (i) => (i % 5 === 4 ? dayLabel(t - 29 + i) : ''))}</div>`;
    },
    settings() {
      const opt = (vals, cur, fmt) => vals.map((v) => `<option value="${v}" ${String(v) === String(cur) ? 'selected' : ''}>${fmt(v)}</option>`).join('');
      return topbar('Налаштування') +
        `<div class="card">
        <div class="field"><label>Категорії</label><div class="chips">${[['B', 'B · легковий'], ['C', 'C · вантажний']].map(([c, l]) => `<button class="chip ${settings.cats.includes(c) ? 'on' : ''}" data-act="cat" data-c="${c}">${l}</button>`).join('')}</div></div>
        <div class="field"><label for="s-new">Нових питань на день</label><select id="s-new" data-set="newPerDay">${opt([10, 20, 30, 40, 50, 70, 100, 150], settings.newPerDay, (v) => v)}</select>
          <p class="muted small">Повторення не обмежуються — щодня робіть усі, що на черзі.</p></div>
        <div class="field"><label for="s-ret">Цільове запам'ятовування</label><select id="s-ret" data-set="retention">${opt([0.9, 0.93, 0.95, 0.97], settings.retention, (v) => Math.round(v * 100) + '%' + (v === 0.95 ? ' (рекомендовано)' : v === 0.97 ? ' (в усмерть, більше повторень)' : ''))}</select>
          <p class="muted small">Питання повертається тоді, коли ймовірність його пригадати падає до цього рівня. Вище — частіші повторення.</p></div>
        <div class="field"><label for="s-exam">Дата іспиту</label><input type="date" id="s-exam" data-set="examDate" value="${esc(settings.examDate)}"></div>
        <div class="field switch"><input type="checkbox" id="s-shuf" data-set="shuffle" ${settings.shuffle ? 'checked' : ''}><label for="s-shuf" style="margin:0">Перемішувати варіанти відповідей</label></div>
        <p class="muted small" style="margin-top:-8px">Щоб запам'ятовувати зміст, а не номер. Питання з відповідями на кшталт «1 та 2» не перемішуються.</p>
        <div class="field"><label for="s-theme">Тема</label><select id="s-theme" data-set="theme">${opt(['auto', 'light', 'dark'], settings.theme, (v) => ({ auto: 'Як у системі', light: 'Світла', dark: 'Темна' }[v]))}</select></div>
        </div>
        <h2>Резервна копія прогресу</h2>
        <div class="card list">
          <button class="btn" data-act="export">Експортувати прогрес</button>
          <button class="btn" data-act="import">Імпортувати прогрес</button>
          <button class="btn bad" data-act="reset">Скинути весь прогрес</button>
        </div>
        <p class="muted small">Питання: ${esc(DATA.source)} (${esc(DATA.scraped)}), ${Q.length} шт. Текст ПДР: zakon.rada.gov.ua (CC BY 4.0). Пояснення згенеровано ШІ — у разі сумніву звіряйтеся з текстом ПДР.</p>`;
    },
    help() {
      return topbar('Як вчити') + `<div class="card">
        <p style="margin-top:0"><b>Метод — інтервальне повторення (FSRS).</b> Для кожного питання застосунок оцінює, наскільки міцно ви його пам'ятаєте, і повертає його рівно тоді, коли ви от-от почнете забувати. Що краще знаєте — то рідше бачите.</p>
        <p><b>Щодня:</b> натисніть «Вчити» і пройдіть усе, що на черзі. 15–30 хвилин на день ефективніше, ніж 3 години раз на тиждень.</p>
        <p><b>Чесно оцінюйте себе.</b> Якщо відповіли правильно, але навмання — тисніть «Вгадав»: питання повернеться завтра. «Легко» — тільки якщо відповідь очевидна миттєво.</p>
        <p><b>Помилки</b> повторюються в тій самій сесії через кілька питань, доки не відповісте правильно, і знову завтра.</p>
        <p><b>Читайте пояснення</b> і тисніть на пункти ПДР — розуміння правила закриває одразу кілька схожих питань.</p>
        <p><b>Шанс скласти іспит</b> рахується з вашої поточної пам'яті по всіх питаннях: на іспиті ${EXAM_SIZE} випадкових питань і можна помилитись не більше ${EXAM_MAX_ERRORS} разів. Ціль — 95%+.</p>
        <p style="margin-bottom:0"><b>Перед іспитом:</b> вкажіть дату в налаштуваннях — побачите, скільки нових на день треба, щоб встигнути, і прогноз на день іспиту. В останні дні — «Найслабші» та пробні іспити.</p></div>`;
    },
  };

  // ---------- actions ----------
  function studyQueue(list, maxNew) {
    // mix topics: random order for both reviews and new cards
    const due = shuffled(dueCards(list).map((q) => q.id));
    const fresh = shuffled(newCards(list).map((q) => q.id)).slice(0, maxNew);
    return interleave(due, fresh);
  }
  const ACTIONS = {
    back() { back(); },
    close() { closeModal(); },
    home() { stack.length = 0; view = null; go('home'); },
    go(el) {
      const p = {};
      if (el.dataset.id) p.id = el.dataset.id;
      if (el.dataset.sec) p.sec = el.dataset.sec;
      go(el.dataset.to, p);
    },
    cat(el) {
      const c = el.dataset.c;
      const has = settings.cats.includes(c);
      if (has && settings.cats.length === 1) { toast('Потрібна хоча б одна категорія'); return; }
      settings.cats = has ? settings.cats.filter((x) => x !== c) : settings.cats.concat(c);
      saveSettings();
      render();
    },
    study() { startSession('study', studyQueue(pool(), newLeftToday()), 'Навчання'); },
    'study-more'() { startSession('study', studyQueue(pool(), 10), 'Навчання'); },
    weak() {
      const t = today();
      const ids = pool().filter((q) => cards[q.id]).sort((a, b) => recall(a.id, t) - recall(b.id, t)).slice(0, 30).map((q) => q.id);
      startSession('drill', ids, 'Найслабші');
    },
    'hard-drill'() {
      const ids = pool().filter((q) => cards[q.id] && cards[q.id].lapses > 0)
        .sort((a, b) => cards[b.id].lapses - cards[a.id].lapses || recall(a.id) - recall(b.id)).slice(0, 30).map((q) => q.id);
      startSession('drill', ids, 'Складні');
    },
    'sec-study'(el) { startSession('study', studyQueue(Q.filter((q) => q.s === el.dataset.id), 20), 'Розділ ' + el.dataset.id); },
    'sec-all'(el) { startSession('drill', shuffled(Q.filter((q) => q.s === el.dataset.id).map((q) => q.id)), 'Розділ ' + el.dataset.id); },
    answer(el) {
      const i = +el.dataset.i;
      if (view.name === 'study') studyAnswer(view.params.s, i);
      else if (view.name === 'exam' && !view.params.state.finished) examAnswer(view.params.state, i);
    },
    grade(el) { studyGrade(view.params.s, +el.dataset.g); },
    next() { studyNext(view.params.s); },
    exam() { startExam(); },
    'exam-go'(el) { view.params.state.cur = +el.dataset.i; render(); },
    'exam-next'() { examNext(view.params.state); },
    'exam-skip'() {
      const st = view.params.state;
      const n = nextUnanswered(st, st.cur);
      if (n >= 0) { st.cur = n; render(); window.scrollTo(0, 0); }
    },
    'exam-finish'() {
      const st = view.params.state;
      const left = st.answers.filter((a) => a == null).length;
      if (left && !confirm(`Без відповіді ${left} ${plural(left, 'питання', 'питання', 'питань')} — вони зарахуються як помилки. Завершити?`)) return;
      finishExam(st);
    },
    'exam-review'(el) { const i = +el.dataset.i; view.params.state.review = i < 0 ? null : i; render(); window.scrollTo(0, 0); },
    'exam-again'() { view = null; stack.length = 0; go('home'); startExam(); },
    rule(el) { showRule(el.dataset.ref, el.dataset.q); },
    'open-pdr'(el) {
      closeModal();
      const num = el.dataset.num;
      go('pdr', { sec: el.dataset.sec });
      const lines = Array.from(document.querySelectorAll('.pdr-line'));
      const hit = lines.find((l) => l.textContent.startsWith(num + ' ') || l.textContent.startsWith(num + '.') || l.textContent.startsWith(num + ' “'));
      if (hit) { hit.classList.add('hit'); hit.scrollIntoView({ block: 'center' }); }
    },
    zoom(el) { openModal(`<img src="img/${el.dataset.img}.webp" alt="" data-act="close">`, 'img'); },
    more() { view.params.limit = (view.params.limit || 40) + 40; render(); },
    export() {
      const data = JSON.stringify({ app: 'pdr-trainer', v: 1, exported: new Date().toISOString(), settings, cards, log, exams: store.get('exams', []) });
      if (window.Android && window.Android.share) { window.Android.share(data); return; }
      openModal(`<h2 style="margin-top:0">Експорт</h2><p class="muted small">Скопіюйте і збережіть цей текст.</p><textarea readonly>${esc(data)}</textarea>
        <p><button class="btn" data-act="close">Закрити</button></p>`);
    },
    import() {
      openModal(`<h2 style="margin-top:0">Імпорт</h2><p class="muted small">Вставте раніше експортований текст. Поточний прогрес буде замінено.</p>
        <textarea id="imp"></textarea><div class="row" style="margin-top:10px"><button class="btn" data-act="close">Скасувати</button><button class="btn primary" data-act="do-import">Імпортувати</button></div>`);
    },
    'do-import'() {
      try {
        const d = JSON.parse(document.getElementById('imp').value);
        if (d.app !== 'pdr-trainer' || !d.cards) throw new Error('bad');
        cards = d.cards; log = d.log || {}; settings = Object.assign({}, DEFAULT_SETTINGS, d.settings || {});
        saveCards(); saveLog(); saveSettings(); store.set('exams', d.exams || []);
        closeModal(); applyTheme(); toast('Прогрес імпортовано'); render();
      } catch (e) {
        toast('Не схоже на файл прогресу');
      }
    },
    reset() {
      if (!confirm('Видалити весь прогрес? Це не можна скасувати.')) return;
      cards = {}; log = {}; saveCards(); saveLog(); store.set('exams', []);
      toast('Прогрес скинуто'); render();
    },
  };

  document.addEventListener('click', (e) => {
    const modal = document.getElementById('modal');
    if (e.target === modal) { closeModal(); return; }
    const el = e.target.closest('[data-act]');
    if (!el || el.disabled) return;
    const fn = ACTIONS[el.dataset.act];
    if (fn) { e.preventDefault(); fn(el); }
  });
  document.addEventListener('change', (e) => {
    const el = e.target.closest('[data-set]');
    if (!el) return;
    const key = el.dataset.set;
    let v = el.type === 'checkbox' ? el.checked : el.value;
    if (key === 'newPerDay') v = +v;
    if (key === 'retention') v = +v;
    settings[key] = v;
    saveSettings();
    if (key === 'theme') applyTheme();
    toast('Збережено');
  });
  let searchTimer = null;
  document.addEventListener('input', (e) => {
    if (e.target.id !== 'search') return;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      view.params.query = e.target.value;
      view.params.limit = 40;
      render();
      const s = document.getElementById('search');
      s.focus();
      s.setSelectionRange(s.value.length, s.value.length);
    }, 250);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') back();
  });

  applyTheme();
  go('home');
  window.__pdr = { cards: () => cards, settings: () => settings, today, readiness, findRule };
})();
