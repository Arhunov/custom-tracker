// Run: node --test pdr-trainer/tests/fsrs.test.js
const test = require('node:test');
const assert = require('node:assert');
const F = require('../web/fsrs.js');

test('new card: Good gives a few days, Easy gives more, Again comes back tomorrow', () => {
  const pv = F.preview(null, 100, { retention: 0.9 });
  assert.strictEqual(pv[1], 1);
  assert.ok(pv[3] >= 3 && pv[3] <= 5, `good=${pv[3]}`);
  assert.ok(pv[4] > pv[3]);
});

test('successful reviews grow the interval, a lapse resets it to one day', () => {
  let c = null;
  let day = 0;
  let prev = 0;
  for (let i = 0; i < 4; i++) {
    c = F.review(c, 3, day, { retention: 0.9 });
    const ivl = c.due - day;
    assert.ok(ivl > prev, `interval should grow: ${prev} -> ${ivl}`);
    prev = ivl;
    day = c.due;
  }
  const s = c.s;
  c = F.review(c, 1, day, { retention: 0.9 });
  assert.strictEqual(c.due - day, 1);
  assert.ok(c.s < s);
  assert.strictEqual(c.lapses, 1);
});

test('higher target retention schedules sooner', () => {
  const c = F.review(null, 3, 0, { retention: 0.9 });
  const lo = F.review(c, 3, c.due, { retention: 0.9 }).due;
  const hi = F.review(c, 3, c.due, { retention: 0.97 }).due;
  assert.ok(hi < lo);
});

test('recall probability is ~retention when the card is due', () => {
  const c = F.review(null, 3, 0, { retention: 0.9 });
  const r = F.recallOn({ ...c }, 0 + F.intervalFor(c.s, 0.9));
  assert.ok(Math.abs(r - 0.9) < 1e-6);
});

test('exam pass probability: 20 questions, at most 2 errors', () => {
  assert.ok(Math.abs(F.passProbability([1], 20, 2) - 1) < 1e-12);
  assert.ok(F.passProbability([0.95], 20, 2) > 0.9);
  assert.ok(F.passProbability([0.9], 20, 2) < 0.7);
});
