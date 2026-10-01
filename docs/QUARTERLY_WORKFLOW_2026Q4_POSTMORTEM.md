# Postmortem — quarterly scoring workflow failure after PR #10 (2026-Q4)

> **Scope:** CI pipeline and the input contract between the scorer and the formula
> workbook. **No model weight, scoring formula, calibration parameter, score band or
> published historical score was changed.**
> Written: 2026-10-01 · Branch: `arena/01a0f781-vn-index-scoring-quarterly-qua`

---

## 1. Symptom

PR #10 was squash-merged to `main` as `bf1da42`. The next two runs of
`📊 VN-Index Quarterly Scoring` both failed on the same commit and the same quarter
(`2026-Q4`):

| Run | Trigger | URL | Failing step |
|---|---|---|---|
| #18 | `schedule` | `actions/runs/36811707592` | 🚀 Run quarterly scoring pipeline |
| #19 | `workflow_dispatch` | `actions/runs/36812137668` | 🚀 Run quarterly scoring pipeline |

Checkout, Python setup, dependency install, quarter detection, artifact upload and the
Pages trigger all succeeded. The commit step was skipped because the single combined
pipeline step exited 1.

## 2. Exact failure

The combined step ran six commands. The first five lines of the step succeeded
(`run_quarterly.py`, `scripts/rebuild_html.py`, `generate_english_master_workbook.py`
printing *"Architecture: 14 sheets"*); the command that exited 1 was:

```
python verify_workbook_accuracy.py
```

Tail of run #19 (run #18 is identical up to live-data noise in the last two decimals):

```
=== AUDIT RESULT ===
FAIL — 13 failure(s) across 8,925 checks
  [FAIL] 2026-Q4 raw score vs JSON: actual=46.199999999999996, expected=46.52, tolerance=0.05
  [FAIL] 2026-Q4 calibrated score vs JSON: actual=30.3, expected=31.1, tolerance=0.05
  [FAIL] 2026-Q4 raw score vs Parquet: actual=46.199999999999996, expected=46.52, tolerance=0.05
  [FAIL] 2026-Q4 calibrated score vs Parquet: actual=30.3, expected=31.1, tolerance=0.05
  [FAIL] 2026-Q4 dispersion mismatch
  [FAIL] 2026-Q4 macro_monetary raw: actual=57.92, expected=58.47, tolerance=0.05
  [FAIL] 2026-Q4 macro_monetary weighted: actual=14.48, expected=14.62, tolerance=0.05
  [FAIL] 2026-Q4 global_intermarket raw: actual=32.42, expected=32.24, tolerance=0.05
  [FAIL] 2026-Q4 valuation_leverage raw: actual=40.39, expected=41.08, tolerance=0.05
  [FAIL] 2026-Q4 valuation_leverage weighted: actual=8.08, expected=8.22, tolerance=0.05
  [FAIL] 2026-Q4 quant_model raw: actual=50.6, expected=51.12, tolerance=0.05
  [FAIL] 2026-Q4 quant_model weighted: actual=7.59, expected=7.67, tolerance=0.05
  [FAIL] 2026-Q4 market_structure raw: actual=55.76, expected=55.67, tolerance=0.05
##[error]Process completed with exit code 1.
```

`actual` = value recomputed by the Excel formula graph, `expected` = value published in
`output/exports/score_2026_Q4.json` / `data/scores/quarterly_scores_history.parquet`.
Only `2026-Q4` failed; 23/24 historical quarters reconciled exactly. There was **no**
API error, **no** `<MISSING>` ML output (`[ASSERT PASS] ML Forecast OK`), **no**
unresolved formula and **no** `XlError`.

## 3. Root cause — two lossy input paths into the formula workbook

`run_quarterly.py` re-scored `2026-Q4` from live data at the quarter end
(`data_as_of = 2026-09-30`, raw 46.52 / calibrated 31.10), replacing the provisional
snapshot committed on 2026-09-28 (`data_as_of = 2026-09-25`, raw 47.67 / calibrated 33.97).
`generate_english_master_workbook.py` then rebuilt the workbook **not** from those live
inputs but from two stand-ins:

1. **Stale audit ledgers.** The workbook sources bonds, FX-Z, M2, P/E–P/B–EYG Z,
   foreign/ETF flow Z and ADTV from
   `data/scores/vnindex_quarterly_{market_data,flows,adtv}.json`. Those files are written
   only by the manual `scripts/backfill_*.py` jobs, so they still contained the
   2026-09-25 values (e.g. ADTV(2026-Q3) = 673,247,880 over 61 sessions, while the live run
   measured 670,735,870 over 63 sessions; `vn1y_yield = 3.8615`, `nff_z = -0.0525`, …).
   Note the price ledger `vnindex_quarterly_close.json` **is** refreshed automatically by
   `report_builder`, which is why the workbook showed the new PIT close (1,768.62) next to
   old pillar inputs — an internally inconsistent mix.

2. **Four-decimal display strings.** Quant-pillar inputs were recovered with regular
   expressions from `group_details` text such as
   `"Forward log-return/day (next ~1M) = -0.0003 → score 45"`. The MLR signal is
   `50 + mlr_pred × 20000`, so 5e-5 of display rounding moves the quant pillar by up to
   **0.5 points — ten times the ±0.05 audit tolerance**. The live forecast was
   `-0.00025130269673105177`; the workbook consumed `-0.0003` and produced 50.6 against
   the published 51.12.

   Historical quarters survived this only by construction: their stored pillar scores were
   themselves re-derived from the same rounded strings by the backfill scripts, so the two
   sides agreed. The first genuinely live scoring run broke the illusion.

3. **Dispersion label basis (same class of bug).** `dispersion_level` was classified by
   comparing the quarter's pillar standard deviation against the `pillar_std` column of
   `quarterly_scores_history.parquet`. That column holds the value of each quarter's
   *original* run and is stale with respect to the pillar scores later published by the
   backfills (it differs in 24/24 quarters), whereas the workbook recomputes the series
   from the published pillars. For `2026-Q4` the two bases straddled the quarter's value
   (p33 = 10.05 workbook-side vs 10.79 parquet-side, value 10.17) and the labels diverged.

Both runs failed for exactly the same reason: they are the same commit, the same quarter
and the same code path — the schedule/dispatch distinction is irrelevant, and the small
differences between the two runs (`32.24` vs `32.23`, `51.12` vs `51.11`) are just live
data and model re-fit noise between 03:44 and 03:49 UTC.

## 4. Fix — publish the exact scorer inputs and consume them

* `compute_quarterly_score()` now publishes `quarterly_score.pit_scorer_inputs`
  (`build_pit_scorer_inputs`, `schema_version = 1`): the full-precision bonds, macro,
  global, flow, valuation, structure and quant inputs it actually used. Missing inputs are
  published as `null` — never as a default.
* `generate_english_master_workbook.py` prefers that contract and falls back to the old
  ledger/regex path per field for quarters published before it. Regenerating the workbook
  from the committed artifacts produces **zero cell differences**.
* `src/scoring/ledger_sync.py` (called by `run_quarterly.py` right after scoring) rewrites
  the audit ledgers for the scored quarter only, from the same inputs, merging rather than
  clobbering backfill-owned keys, and is idempotent.
* The dispersion percentile basis is recomputed from the published pillar scores
  (`published_pillar_std_history`), i.e. the same quantity the workbook derives.
* The workflow runs each generation/verification command as its own named step, so the next
  failure names itself; the commit and Pages-deploy steps run only when every gate is green.

## 5. Verification

Offline reproduction (Python 3.11, committed artifacts, no live API): re-score `2026-Q4`
at `2026-09-30` with run #19's full-precision model outputs while leaving the ledgers at
the 2026-09-25 snapshot.

| | before fix | after fix |
|---|---|---|
| `verify_workbook_accuracy.py` | `FAIL — 11–13 failures` incl. `quant_model raw: actual=50.6, expected=51.12` | `PASS — 8,925 checks; 24/24 quarters within ±0.05` |

`tests/test_live_refresh_reconciliation.py` keeps that scenario in CI;
`tests/test_pit_input_contract.py` and `tests/test_ledger_sync.py` pin the contracts.
