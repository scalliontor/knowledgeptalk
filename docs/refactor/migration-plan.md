# Migration plan — THIN SERVER + CORE-IN-REPO (retrieval layer)

Source of truth: `docs/project_state/2026-06-22-canonical.md`. This plan covers
moving the extracted `packages/retrieval` + `apps/companion_api/server.py` thin
server onto the production server and proving behavior parity vs the monolith
**before** any promote. It is gated by backtest (anchor ≥ 97.0 · guard ≥ 98.1 ·
real cruft = 0 · error = 0 · P95 in range) per the canonical release gate.

Runtime fact (canonical §"Thực tế hạ tầng"): the live RAG is a single file on the
server — `rag_server.py` (:8888 prod) / `rag_server_canary.py` (:8889) at
`/home/namnx/Ptalk_project/CloudPTalk`. The merged candidate is `/tmp/rag_server_merged.py`
(test :8890, keeps moderation). Nothing in this repo is on the serve path yet.

## What was extracted (this PR)

| Repo file | Replaces (monolith fn) | Deps injected |
|---|---|---|
| `packages/retrieval/lesson_card.py` | `query_lesson_card` + content-vec loop | `driver_factory`, `model`, `fold`, `classify_intent`(1-arg), `is_recite`, `sanitize`, `neo4j_uri/auth`; pure `_pick_content_vec(cands, qv)` |
| `packages/retrieval/structured.py` | `query_structured_exact`, `query_concept_exact` | `driver_factory` |
| `packages/retrieval/neo4j_queries.py` | `query_neo4j_vector/_knowledge_chunk/_lesson_guide`, `recite_from_literature_text/_reading_text/_full_document` | `driver_factory`, `model`, `lines_payload` |
| `packages/retrieval/vector.py` | `query_qdrant` (+ `SUBJECT_TO_QDRANT`) | `model` |
| `apps/companion_api/server.py` | thin shell for `rag_server_canary.py` | wires `knowledge_core` + `retrieval` |

Cypher strings + scoring/ORDER-BY are byte-for-byte. The only behavioral risk is
the injection wiring, which the compare harness (`scripts/compare_monolith_vs_thin.py`)
exists to catch.

## Step 0 — prerequisites (do NOT skip)

1. Backtest Engineer + Repo Cartographer steps done (canonical execution order).
2. Characterization golden for `knowledge_core` green (already in
   `tests/characterization/`). `tests/test_retrieval_scoring.py` green locally.
3. Neo4j backup verified (release gate). Note current prod Git SHA.
4. Pick a low-traffic window; ESP32 downtime only at the FINAL restart, not during
   side-by-side compare.

## Step 1 — sync packages next to the runtime (no overwrite)

Copy the repo packages + thin server to the server **alongside** the monolith,
never over it. Suggested layout on server:

```
/home/namnx/Ptalk_project/CloudPTalk/
  rag_server.py                 # prod :8888  (UNTOUCHED)
  rag_server_canary.py          # :8889       (UNTOUCHED)
  /tmp/rag_server_merged.py     # :8890 merged baseline (UNTOUCHED)
  thin/                         # NEW — synced from repo
    packages/knowledge_core/...
    packages/retrieval/...
    apps/companion_api/server.py
```

Transfer with a single `scp -r` (canonical: SSH flaky w/ fail2ban — one command,
keep launch separate). Do NOT use inline-SSH heredocs to launch (canonical:
"LAUNCH METHOD = script file + nohup; inline ssh fails").

## Step 2 — make packages importable on the server

Two options; pick ONE and record it in the release note:

- **PYTHONPATH (lowest-risk, reversible):**
  `export PYTHONPATH=/home/namnx/Ptalk_project/CloudPTalk/thin/packages`
  then run uvicorn with module path `apps.companion_api.server:app`
  (cwd = `.../thin`).
- **editable install:** add a minimal `setup.cfg`/`pyproject` in `thin/` and
  `pip install -e .` into the server venv (Python 3.8). Heavier; only if PYTHONPATH
  proves brittle.

Reconcile config first: `NEO4J_URI/NEO4J_AUTH`, `HF_HOME`, Qdrant/PG hosts in
`apps/companion_api/server.py` must match the live monolith. **TODO before launch:**
move these out of the literal into the server `.env` (CLAUDE.md: never commit
secrets; the merged/monolith values currently live in the file verbatim only to
preserve behavior during extraction).

## Step 3 — port the moderation endpoint (BLOCKER for promote, not for compare)

`/v2/moderation/expand-topic` is **server-only** (canary lacks it; merged has it).
The thin server ships a TODO stub. Before promote to :8888, copy the endpoint body
VERBATIM from `/tmp/rag_server_merged.py` into `apps/companion_api/server.py` and
re-extract any helper it needs into `packages/` the same injected way. Until then
the thin server is compare-able on the `/retrieve` + `/v2/rag/retrieve` paths only.

## Step 4 — launch thin server on a TEMP port (8891)

Use a launch script + `nohup` (BGE load ~30s). Example `thin/launch_8891.sh`:

```
cd /home/namnx/Ptalk_project/CloudPTalk/thin
export PYTHONPATH=$PWD/packages
nohup python -m uvicorn apps.companion_api.server:app \
  --host 0.0.0.0 --port 8891 > /tmp/thin_8891.log 2>&1 &
```

Wait until `/health` on 8891 returns `{"status":"ok"}` (BGE loaded). Keep monolith
candidate live on 8890 the whole time.

## Step 5 — side-by-side compare (8890 monolith vs 8891 thin)

Run `scripts/compare_monolith_vs_thin.py` (documented in that file; NOT run in this
PR). It replays identical cases against both ports and diffs `intent.tier`,
`intent.work_name`, and `context`. Acceptance: 100% match on `tier` + `work_name`
for the anchored set; `context` byte-equal (NFC-normalized) on the lesson-card /
tier-A paths. Any mismatch ⇒ STOP, fix wiring, repeat.

## Step 6 — full sweep gate on the thin server

Re-run the full sweep (`scripts/run_full_sweep.sh`, pointed at 8891). Must hit the
canonical gate: anchor ≥ 97.0, guard ≥ 98.1, real cruft = 0, error = 0, P95 in
range, Toán 4–6 & Lịch sử not regressed, volume collision 0 critical. Store under
`reports/backtest/<run>/`. No report + diff ⇒ no merge (canonical invariant).

## Step 7 — promote (only after Steps 5+6 pass AND moderation ported)

Follow `docs/operations/release-checklist.md`. Restart :8888 with the thin server
(script + nohup), then post-release smoke. Record Git SHA + rollback command in the
release note.

## Risks

- **Injection drift** — a dep wired wrong (e.g. `classify_intent` not bound to
  model, or `driver_factory` pointing at the wrong bolt URI) silently changes
  anchor/guard. Mitigation: Step 5 compare must be byte-equal before Step 6.
- **Orchestrator not yet extracted** — `retrieve()` is inlined in the thin server
  (TODO ORCH). It mirrors the monolith order but is a second copy until
  `packages/rag_router` lands; keep them in sync or the compare will catch a drift.
- **Config divergence** — server `.env`/hosts differ from the literals in
  `server.py` (canonical: server source-of-truth differs). Reconcile in Step 2.
- **Moderation gap** — promoting without porting the endpoint breaks the
  moderation route the client may call. Step 3 is a hard blocker for :8888.
- **Python 3.8 venv** — packages are 3.8-safe (no 3.9+ syntax in extracted code);
  re-confirm `py_compile` in the server venv after sync.
- **SSH/fail2ban** — batch transfers; single commands; launch via script not inline.

## Rollback

- Thin server is on a separate port (8891) and a separate `thin/` dir — it touches
  nothing on :8888/:8889/:8890. Rollback of the *experiment* = `kill` the 8891 pid.
- For a promoted :8888 thin server: keep the previous `rag_server.py` + its Git SHA;
  rollback = stop thin, relaunch the old `rag_server.py` via its launch script.
  Document the exact `kill`/relaunch commands in the release note (gate item).
- Neo4j unaffected by this PR (read-only retrieval); the 2026-06-22 data fix is
  already live and independent.
