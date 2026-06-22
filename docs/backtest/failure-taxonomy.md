# Backtest Failure Taxonomy (A–O) — Knowledge PTalk

> A fixed vocabulary for *what broke*. Every backtest failure classifies into
> exactly one class. Implemented in
> [`packages/backtest/failure_taxonomy.py`](../../packages/backtest/failure_taxonomy.py)
> (`classify_failure(case) -> (code, reason)`), histogrammed by `classify_run`.
> Pairs with [`metric-definitions.md`](metric-definitions.md).

A **failure** = a case that did not pass its own criterion: a lesson case with
wrong anchor or wrong mode, or a guard case that emitted a card. The classifier
is ordered (first match wins), most-specific → most-general, so e.g. a long-math
title miss is **E**, not the catch-all **B**.

| Code | Name | Signal | What it means | Primary fix surface |
|------|------|--------|---------------|---------------------|
| **A** | Missing client context | `has_client_context = false`, no card | Client sent `{}` — no `current_lesson`/`trang`/`tập`, so nothing to anchor on; system correctly declined. Not a model bug, a **contract** gap. | Client `rag_client` must send context (canonical gap #4). |
| **B** | Wrong scope | Card from a different subject / grade / book than expected | Retrieval crossed the scope boundary (môn+lớp+bộ sách+tập). | Scope filter / structured pre-filter. |
| **C** | Volume collision | Anchor miss + `got_volume != expected_volume` (often same page) | Page reset between tập 1/2 resolved to the wrong volume. | `tap_no`-aware page lookup. |
| **D** | Title normalization | Got≈expected after stripping punctuation/whitespace, raw differs | Title match broke on a comma/space/quote difference. | Extend `norm()` / title cleanup at ingest. |
| **E** | Long math title | Expected title is long (≥45 chars) or formula-like (`=`,`phân số`,`đa thức`,…) | Long/symbolic Toán titles drift the anchor. **The #1 real gap** (Toán 4–6 = 86%). | Math-title parser / alias table. |
| **F** | Page ambiguity | Page-anchored (`trang_query`/`trang_profile`) miss to a neighbour lesson | Two lessons share/overlap a page range; the boundary is ambiguous. | Boundary-aware trang ranges. |
| **G** | Vector overrode structured | A structured-cue case (`current_lesson`/`name`/`trang`) answered by content-vector to a wrong lesson | The vector fallback fired when a structured anchor existed and should have won. | Enforce structured-first routing order. |
| **H** | Work-name normalization | Got≈expected but raw differs by **roman numeral / dash / year** | `work_name_norm` mishandles "Bài III", "1945–1954", dashes. Suspected Lịch sử 95.5% cause. | `work_name_norm` rules for roman/dash/year. |
| **I** | Intent route | Anchor correct, **mode/tier wrong** (e.g. recite asked, card served) | Right lesson, wrong action (giảng vs đọc vs luyện). | Intent classifier / tier selection. |
| **J** | False refusal | In-scope answerable lesson case got **no card** | System refused something it could answer — the silent UX failure; drags `refusal_precision`. | Loosen over-tight guards on in-scope queries. |
| **K** | Missed refusal | Guard case **emitted a card** | Answered chitchat / out-of-book / trap instead of refusing — a hallucination risk. | Tighten guards (out-of-book, trap-word/year, OOB-trang). |
| **L** | Real cruft | Emitted card whose context has a **genuine** source leak (`vietjack`, `Giáo viên VietJack`, `(Giáo viên …)`, `loigiaihay`, …) | Source leaked into the answer — violates "sạch nguồn". Baseline count = 0. | Ingest-time source stripping. |
| **M** | Cruft false-positive | Loose `giáo viên` keyword matched but **no real leak** | The historical "204" artifact — legitimate civics vocabulary mis-flagged. **Not a behavioral failure**; surfaced so the harness stops miscounting it. | Already fixed: tightened keyword (this toolkit). |
| **N** | Runtime error | `/retrieve` raised | Server error / timeout / malformed response. Baseline = 0. | Server stability / input validation. |
| **O** | Latency regression | Case latency over budget (single case > 400 ms), or run-level p95 rise | Slow serve path; per-case tag for the latency histogram, plus the run-level p95 regression check in `compare_runs`. | Profile serve path; keep it Gemma-free. |

## Classifier ordering (why first-match matters)

```
N runtime error
└─ L real cruft on card        ─┐ (cruft checked before behavior: a leak is a leak
└─ M false-positive cruft       │  regardless of whether the anchor was right)
guard case:  pass | K missed refusal
lesson case:
  anchor OK → (pass | I intent/mode)
  anchor MISS:
    no card → (A missing-context | J false refusal)
    card:    C volume → F page → E long/math → H roman/dash/year → D punct → G vector → B scope
```

## How to use it

- **Per-run histogram** — `failure_taxonomy.classify_run(cases)` over live
  case-results gives `{code: count}`. A spike in one class names the work item
  (e.g. lots of **E** ⇒ go fix Toán title parsing; lots of **K** ⇒ tighten guards).
- **Mapping classes to gaps** — the canonical gaps map to classes: Toán 4–6 →
  **E** (+ some **G**/**D**); Lịch sử → **H**; client `{}` → **A**; "204 cruft" →
  **M** (and real cruft would be **L**).
- **What needs raw context** — **L/M** need the served context string, which the
  2026-06-17 aggregate reports do not store. Classify L/M on **live** case-results;
  on old reports they appear only as the aggregate false-positive count.

## Inputs the classifier reads (per case)

Required: `error`, `expected_work` (None ⇒ guard), `got_tier`, `got_work`.
Optional (improve precision): `context`, `expected_tier`, `dim`, `page`,
`expected_volume`/`got_volume`, `expected_subject`/`got_subject`,
`has_client_context`, `latency_ms`. Missing optionals degrade gracefully toward
the general classes (B / J).
