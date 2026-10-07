/*
 * FSRS-4.5 spaced-repetition scheduler (same model Anki uses), day granularity.
 * Card state: {s: stability (days), d: difficulty 1..10, last: day of last review,
 *              due: day the card is due, reps, lapses}. A missing state = new card.
 * Grades: 1 = Again (wrong / guessed), 2 = Hard, 3 = Good, 4 = Easy.
 */
(function (root) {
  const W = [0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031, 1.6474,
    0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755];
  const DECAY = -0.5;
  const FACTOR = 19 / 81;
  const clampD = (d) => Math.min(10, Math.max(1, d));

  function retrievability(elapsedDays, s) {
    return Math.pow(1 + FACTOR * Math.max(0, elapsedDays) / s, DECAY);
  }

  function initDifficulty(g) {
    return clampD(W[4] - (g - 3) * W[5]);
  }

  function nextDifficulty(d, g) {
    return clampD(W[7] * initDifficulty(4) + (1 - W[7]) * (d - W[6] * (g - 3)));
  }

  function recallStability(d, s, r, g) {
    const hard = g === 2 ? W[15] : 1;
    const easy = g === 4 ? W[16] : 1;
    return s * (1 + Math.exp(W[8]) * (11 - d) * Math.pow(s, -W[9]) *
      (Math.exp(W[10] * (1 - r)) - 1) * hard * easy);
  }

  function forgetStability(d, s, r) {
    const fs = W[11] * Math.pow(d, -W[12]) * (Math.pow(s + 1, W[13]) - 1) * Math.exp(W[14] * (1 - r));
    return Math.min(s, fs);
  }

  /** Days until recall probability drops to `retention`. */
  function intervalFor(s, retention) {
    return s / FACTOR * (Math.pow(retention, 1 / DECAY) - 1);
  }

  /** Recall probability of a card on `day` (0 for unseen cards). */
  function recallOn(card, day) {
    if (!card || !card.reps) return 0;
    return retrievability(day - card.last, card.s);
  }

  /**
   * Apply a review. Returns a new card state; does not mutate `card`.
   * opts: {retention: 0.7..0.99, fuzz: 0..1 (random number, 0.5 = no fuzz)}
   */
  function review(card, grade, today, opts) {
    const retention = opts && opts.retention ? opts.retention : 0.9;
    let s, d, reps, lapses;
    if (!card || !card.reps) {
      s = W[grade - 1];
      d = initDifficulty(grade);
      reps = 1;
      lapses = grade === 1 ? 1 : 0;
    } else {
      const r = retrievability(today - card.last, card.s);
      d = nextDifficulty(card.d, grade);
      s = grade === 1 ? forgetStability(card.d, card.s, r) : recallStability(card.d, card.s, r, grade);
      reps = card.reps + 1;
      lapses = card.lapses + (grade === 1 ? 1 : 0);
    }
    s = Math.max(0.1, s);
    let ivl;
    if (grade === 1) {
      ivl = 1; // a forgotten card always comes back tomorrow
    } else {
      ivl = intervalFor(s, retention);
      if (ivl > 2 && opts && typeof opts.fuzz === 'number') {
        ivl *= 1 + (opts.fuzz - 0.5) * 0.1; // ±5% to spread the load
      }
      ivl = Math.max(1, Math.round(ivl));
    }
    return { s: +s.toFixed(4), d: +d.toFixed(4), last: today, due: today + ivl, reps, lapses };
  }

  /** Interval (days) each grade would give — for button hints. */
  function preview(card, today, opts) {
    const out = {};
    for (const g of [1, 2, 3, 4]) out[g] = review(card, g, today, opts).due - today;
    return out;
  }

  /** P(at most `maxErrors` errors among `n` random questions) given per-question recall probs. */
  function passProbability(probs, n, maxErrors) {
    if (!probs.length) return 0;
    const q = 1 - probs.reduce((a, b) => a + b, 0) / probs.length;
    let p = 0;
    for (let k = 0; k <= maxErrors; k++) p += binom(n, k) * Math.pow(q, k) * Math.pow(1 - q, n - k);
    return p;
  }

  function binom(n, k) {
    let r = 1;
    for (let i = 1; i <= k; i++) r = r * (n - k + i) / i;
    return r;
  }

  const api = { review, preview, retrievability, recallOn, intervalFor, passProbability, W };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.FSRS = api;
})(typeof window !== 'undefined' ? window : globalThis);
