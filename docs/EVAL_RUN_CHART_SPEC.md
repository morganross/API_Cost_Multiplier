# Evaluation Run Chart Specification

This document describes how to programmatically generate the complete evaluation run chart by reading the configuration files.

---

## Configuration Sources

| Config File | Purpose |
| :--- | :--- |
| `api_cost_multiplier/config.yaml` | Main config: generators, combiners, eval settings |
| `api_cost_multiplier/llm-doc-eval/config.yaml` | Judge models for evaluation |
| `api_cost_multiplier/llm-doc-eval/criteria.yaml` | Criteria list (affects DB rows, not run count) |

---

## Chart Structure

The chart has **5 phases** executed in order:

### Phase 1: PRE-COMBINE SINGLE EVAL

| Field | Source | Path |
| :--- | :--- | :--- |
| **Files to evaluate** | `config.yaml` | `runs[]` (count of entries) |
| **Judge models** | `llm-doc-eval/config.yaml` | `models` (keys = judge IDs) |

**Formula:** `len(runs) × len(judges)`

**Chart Row Template:**
```
| # | precombine-single-eval | {judge_id} | {run.type} {run.provider}:{run.model} |
```

**Loop Order:** Judge → File (outer to inner)

---

### Phase 2: PRE-COMBINE PAIRWISE EVAL

| Field | Source | Path |
| :--- | :--- | :--- |
| **Candidates** | Derived | Top N from Phase 1 single scores |
| **N value** | `config.yaml` | `eval.pairwise_top_n` |
| **Judge models** | `llm-doc-eval/config.yaml` | `models` |

**Formula:** `C(pairwise_top_n, 2) × len(judges)` where C(n,2) = n*(n-1)/2

For `pairwise_top_n: 3`: C(3,2) = 3 pairs

**Chart Row Template:**
```
| # | precombine-pairwise-eval | {judge_id} | Top #{i} vs Top #{j} |
```

**Loop Order:** Judge → Pair

---

### Phase 3: COMBINER (FPF Generation)

| Field | Source | Path |
| :--- | :--- | :--- |
| **Enabled** | `config.yaml` | `combine.enabled` |
| **Combiner models** | `config.yaml` | `combine.models[]` |
| **Input reports** | Derived | Top 2 from Phase 1 (hardcoded in `combiner.get_top_reports(..., limit=2)`) |

**Formula:** `len(combine.models)` (one combined doc per model)

**Chart Row Template:**
```
| # | combiner-generation | {combine.models[i].provider}:{combine.models[i].model} | Combine Top 3 → New Doc |
```

**Code Reference:** `runner.py` line 1134: `combiner.get_top_reports(db_path, output_folder, limit=2)`

---

### Phase 4: POST-COMBINE SINGLE EVAL

| Field | Source | Path |
| :--- | :--- | :--- |
| **Files to evaluate** | Derived | Top 2 old (from Phase 1) + N new (from Phase 3) |
| **N new files** | `config.yaml` | `len(combine.models)` |
| **Judge models** | `llm-doc-eval/config.yaml` | `models` |

**Formula:** `(2 + len(combine.models)) × len(judges)`

For 2 combiner models: (2 + 2) × 2 = 8 runs

**Chart Row Template:**
```
| # | postcombine-single-eval | {judge_id} | Pre-combine Top #{k} |  (for k in 1..2)
| # | postcombine-single-eval | {judge_id} | Combined {combine.models[i].provider}:{combine.models[i].model} |
```

**Code Reference:** `runner.py` line 1164: `tournament_pool = top_reports + combined_files`

---

### Phase 5: POST-COMBINE PAIRWISE EVAL

| Field | Source | Path |
| :--- | :--- | :--- |
| **Candidates** | Derived | Top N from Phase 4 scores (pool of 4) |
| **N value** | `config.yaml` | `eval.pairwise_top_n` |
| **Judge models** | `llm-doc-eval/config.yaml` | `models` |

**Formula:** `C(min(pairwise_top_n, pool_size), 2) × len(judges)`

For pool=4, top_n=3: C(3,2) × 2 = 3 × 2 = 6 runs

**Chart Row Template:**
```
| # | postcombine-pairwise-eval | {judge_id} | Post Top #{i} vs Post Top #{j} |
```

---

## Total Run Count Formula

```
TOTAL = 
    (len(runs) × len(judges))                           # Phase 1
  + (C(pairwise_top_n, 2) × len(judges))                # Phase 2
  + (len(combine.models))                                # Phase 3
  + ((2 + len(combine.models)) × len(judges))           # Phase 4
  + (C(min(pairwise_top_n, 2+len(combine.models)), 2) × len(judges))  # Phase 5
```

---

## Config Value Locations (JSON Paths)

| Variable | File | JSON Path |
| :--- | :--- | :--- |
| `runs` | `config.yaml` | `$.runs` |
| `runs[i].type` | `config.yaml` | `$.runs[i].type` |
| `runs[i].provider` | `config.yaml` | `$.runs[i].provider` |
| `runs[i].model` | `config.yaml` | `$.runs[i].model` |
| `combine.enabled` | `config.yaml` | `$.combine.enabled` |
| `combine.models` | `config.yaml` | `$.combine.models` |
| `combine.models[i].provider` | `config.yaml` | `$.combine.models[i].provider` |
| `combine.models[i].model` | `config.yaml` | `$.combine.models[i].model` |
| `pairwise_top_n` | `config.yaml` | `$.eval.pairwise_top_n` |
| `eval.mode` | `config.yaml` | `$.eval.mode` |
| `judges` | `llm-doc-eval/config.yaml` | `$.models` |
| `judges[key].provider` | `llm-doc-eval/config.yaml` | `$.models.{key}.provider` |
| `judges[key].model` | `llm-doc-eval/config.yaml` | `$.models.{key}.model` |

---

## Hardcoded Values in Code

| Value | Location | Description |
| :--- | :--- | :--- |
| `limit=2` | `runner.py:1134` | Top 2 reports passed to combiner |
| `limit=2` | `combiner.py:49` | Default limit for `get_top_reports()` |

---

## Example Calculation (Current Config)

**Inputs:**
- `len(runs)` = 6 (2 FPF + 2 GPTR + 2 DR)
- `len(judges)` = 2 (`google_gemini-2.5-flash`, `openai_gpt-5-mini`)
- `len(combine.models)` = 2
- `pairwise_top_n` = 3

**Calculation:**
| Phase | Formula | Result |
| :--- | :--- | :--- |
| Phase 1 | 6 × 2 | 12 |
| Phase 2 | C(3,2) × 2 = 3 × 2 | 6 |
| Phase 3 | 2 | 2 |
| Phase 4 | (2 + 2) × 2 = 4 × 2 | 8 |
| Phase 5 | C(3,2) × 2 = 3 × 2 | 6 |
| **Total** | | **34** |

---

## Chart Generation Pseudocode

```python
def generate_eval_run_chart(main_config, eval_config):
    runs = main_config['runs']
    judges = list(eval_config['models'].keys())
    combine_models = main_config.get('combine', {}).get('models', [])
    combine_enabled = main_config.get('combine', {}).get('enabled', False)
    pairwise_top_n = main_config.get('eval', {}).get('pairwise_top_n', 3)
    
    chart = []
    run_num = 0
    
    # Phase 1: Pre-combine Single Eval
    for judge in judges:
        for run in runs:
            run_num += 1
            chart.append({
                'num': run_num,
                'phase': 'precombine-single-eval',
                'judge': judge,
                'target': f"{run['type']} {run['provider']}:{run['model']}"
            })
    
    # Phase 2: Pre-combine Pairwise Eval
    pairs = list(combinations(range(1, pairwise_top_n + 1), 2))
    for judge in judges:
        for (i, j) in pairs:
            run_num += 1
            chart.append({
                'num': run_num,
                'phase': 'precombine-pairwise-eval',
                'judge': judge,
                'target': f"Top #{i} vs Top #{j}"
            })
    
    # Phase 3: Combiner Generation
    if combine_enabled:
        for cm in combine_models:
            run_num += 1
            chart.append({
                'num': run_num,
                'phase': 'combiner-generation',
                'judge': f"{cm['provider']}:{cm['model']}",
                'target': 'Combine Top 3 → New Doc'
            })
    
    # Phase 4: Post-combine Single Eval
    if combine_enabled:
        pool_size = 2 + len(combine_models)
        for judge in judges:
            # Old top 2
            for k in range(1, 3):
                run_num += 1
                chart.append({
                    'num': run_num,
                    'phase': 'postcombine-single-eval',
                    'judge': judge,
                    'target': f"Pre-combine Top #{k}"
                })
            # New combined
            for cm in combine_models:
                run_num += 1
                chart.append({
                    'num': run_num,
                    'phase': 'postcombine-single-eval',
                    'judge': judge,
                    'target': f"Combined {cm['provider']}:{cm['model']}"
                })
    
    # Phase 5: Post-combine Pairwise Eval
    if combine_enabled:
        post_top_n = min(pairwise_top_n, pool_size)
        post_pairs = list(combinations(range(1, post_top_n + 1), 2))
        for judge in judges:
            for (i, j) in post_pairs:
                run_num += 1
                chart.append({
                    'num': run_num,
                    'phase': 'postcombine-pairwise-eval',
                    'judge': judge,
                    'target': f"Post Top #{i} vs Post Top #{j}"
                })
    
    return chart
```

---

## Notes

1. **Criteria count** affects database rows per run, NOT run count. Each single-eval run produces `len(criteria)` rows.
2. **Mode `both`** means both single and pairwise phases run. If `mode: single`, skip pairwise phases. If `mode: pairwise`, skip single phases (but this breaks the pipeline since pairwise needs single scores first).
3. **`is_combined_run=True`** in `trigger_evaluation_for_all_files()` prevents infinite recursion (no second combiner pass).
