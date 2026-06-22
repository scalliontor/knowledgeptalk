# Backtest Metric Definitions — Knowledge PTalk

> Precise definition of every number the backtest emits. Implemented in
> [`packages/backtest/metrics.py`](../../packages/backtest/metrics.py); scored
> identically to `rag_edu/scripts/schema_v3_2026_06/backtest_book.py`.

## Vocabulary

- **case** — one `(utterance, user_profile)` sent to `/retrieve`.
- **lesson case** — a case with an expected `:Lesson.work_name`. `expected_work != None`.
- **guard case** — a case that should be **refused** (chitchat / offtopic /
  out-of-book / out-of-page / trap). `expected_work == None`.
- **tier** — the serving tier `/retrieve` returns. `CARD_TIERS =
  {lesson_card, lesson_practice, lesson_recite}`. Anything else
  (`none`, `noncard`, …) means "no card emitted" = a refusal.
- **emit a card** — returned `tier ∈ CARD_TIERS`.
- **`norm(x)`** — diacritic-folding normaliser (`đ→d`, strip combining marks,
  lowercase, trim). Two titles "match" iff `norm(a) == norm(b)`.

---

## anchor_at_1
**Did we anchor the correct lesson?** For a lesson case:
`anchor_ok = norm(work_name_returned) == norm(expected_work)`.
`anchor_at_1 = correct_anchors / lesson_cases` (errored cases excluded).

We report **two** anchor figures:

- **`anchor_at_1` (production/anchored path)** — *excludes the `content_only`
  dimension*. This is the canonical **97.0%** and the **gate metric**. Rationale:
  `content_only` (utterance describes the lesson but never names it, no client
  anchor) is *refuse-by-design*; in production the client always sends
  `current_lesson`, so this dimension does not occur. Including it would penalize
  correct refusals.
- **`anchor_all`** — includes `content_only`. ~85% on the baseline. Informational
  / conservative; **not** the gate.

> Reconciliation on the 2026-06-17 baseline: incl. `content_only` = 85.4%,
> excl. = **97.5%** (≈ canonical 97.0%).

## mode_accuracy
**Did we serve in the right mode?** `mode_ok = anchor_ok AND tier == expected_tier`
(e.g. a "đọc thuộc" request must return `lesson_recite`, a "luyện tập" request
`lesson_practice`). `mode_accuracy = mode_ok / lesson_cases`. Always ≤ anchor_at_1.

## guard_accuracy  (== refusal_recall)
**Of the cases that SHOULD be refused, how many were?**
`guard_ok = tier ∉ CARD_TIERS` for a guard case.
`guard_accuracy = guard_ok / guard_cases`. This is exactly `refusal_recall`
(named twice so reports can speak precision/recall).

## refusal_precision
**Of all refusals the system MADE, how many were correct?**
`refusal_precision = correct_refusals / all_refusals`, where a *refusal* is any
case (lesson or guard) that emitted no card, and *correct* means it was a guard
case. Low precision ⇒ the system is refusing in-scope answerable questions
(**false refusals**, taxonomy class J) — the silent failure that frustrates
users. Track precision and recall together: high recall + low precision = "refuses
too much".

## volume_collision_rate
**When we anchor the wrong lesson, how often is it the OTHER volume (tập) of the
same book?** Page numbers reset between tập 1 and tập 2, so a page-anchored query
can resolve to the wrong volume. Over anchor-miss-with-card cases that carry
volume info: `collisions / misses` where `got_volume != expected_volume`.
The invariant "không trùng tập 1/2" requires this to stay ~0 on split books
(baseline: toán 8 KNTT t1=96.4% / t2=98.8% — separation holds).

## source_cruft_real  ·  source_cruft_test_false_positive  (the correction)
**Why two cruft metrics?** The historical "**204 cruft**" in the 2026-06-17 sweep
was a **FALSE POSITIVE**. `backtest_book.py`'s leak list contained the bare
keyword `"giáo viên"`, which matches **legitimate** content — GDCD/civics lessons
discuss thầy cô / giáo viên. Direct Neo4j verification over all 1852 theory chunks:

```
vietjack = 0 · "xem lời giải" = 0 · "video giải" = 0 · loigiaihay = 0
"giáo viên" = 11 (all legitimate vocabulary)
```

→ **Real source cruft = 0.** The "sạch nguồn" goal is met. We therefore split:

- **`source_cruft_real`** — count of emitted cards whose served context contains a
  **genuine** leak. Leak patterns are **tightened** so the bare word
  `giáo viên` no longer fires: only `vietjack`, `loigiaihay`, `xem lời giải`,
  `video giải`, `hay nhất, chi tiết`, `cô ngô`, and the *attribution* forms
  **`Giáo viên VietJack`** / **`(Giáo viên …)`** count. **Gate: must be 0.**
- **`source_cruft_test_false_positive`** — count flagged by the loose `giáo viên`
  keyword but with **no** real leak. Informational; this is what produced "204".

| context string | loose keyword? | real leak? | counted as |
|---|---|---|---|
| `…tôn trọng thầy cô giáo viên…` | yes | no | **false positive** |
| `…Soạn bài hay nhất - Giáo viên VietJack…` | yes | **yes** | **real cruft** |
| `…(Giáo viên: Cô Ngô) trang 12…` | yes | **yes** | **real cruft** |
| `…nguồn: vietjack.me…` | no | **yes** | **real cruft** |
| `…Tự lập là tự làm lấy công việc…` | no | no | clean |

Cruft is only counted when a **card was emitted** (a leak in a refusal context is
not a served-card leak).

> **Report-level caveat:** the 2026-06-17 JSONs store only the aggregate
> `cruft_on_cards`, not the raw context strings, so real-vs-false-positive cannot
> be re-derived from text at report level. Per the verified canonical correction,
> the reporter maps legacy `cruft_on_cards` → `source_cruft_test_false_positive`
> and asserts `source_cruft_real = 0`. **Live** runs (case-level results with
> contexts) compute both directly from `metrics.source_cruft_real/...`.

## error_count
Cases where the `/retrieve` call raised. **Gate: 0.** Baseline: 0 / ~40k.

## latency p50 / p95 / p99
Wall-clock ms per `/retrieve`. Nearest-rank percentiles over all timed cases.
Serve path is Gemma-free; baseline range p95 **193–368 ms** (one outlier book
444 ms). The gate evaluates the **median-book p95** (≤ 400 ms), surfacing the
worst book as a watch item rather than failing on a single outlier.

## path_breakdown
Per-served-tier histogram: `{tier: {n, anchor%}}`. Shows *which routing path*
served each answer (structured `lesson_card` vs `lesson_practice`/`recite` vs
refusals) and its anchor quality — useful to see if a regression shifts mass onto
the wrong path (e.g. vector overriding structured).

## slice_anchor
Per-slice (default `dim`) `{n, anchor%, mode%, cruft_real, cruft_fp}`. Mirrors the
report `by_dimension` block and adds the cruft split. This is the table that
surfaces weak slices (Toán 4–6, Lịch sử 9) and the dimensions where
false-positive cruft clusters.

---

## Gate summary (release)

| Metric | Threshold |
|--------|-----------|
| `anchor_at_1` (production path) | ≥ 97.0 |
| `guard_accuracy` | ≥ 98.1 |
| `source_cruft_real` | = 0 |
| `error_count` | = 0 |
| latency p95 (median book) | ≤ 400 ms |
| per-book anchor regression | ≤ 0.5 pp drop |
| per-book guard regression | ≤ 0.5 pp drop |
| per-book p95 regression | ≤ 50 ms rise |
| volume collision (split books) | 0 critical |
