# Models in registries NOT tested in last run — UPDATED
Date: 2025-10-04 21:29 (local)

Per your instruction, the following failed-run models have been removed from the provider registries (backups exist where applicable):

Removed from registries (removed now)
- openai: codex-mini
- openai: o3-pro
- openai: o1-preview
- google_genai: gemini-live-2.5-flash-preview
- anthropic: claude-opus-4-20250514-thinking

Notes:
- Backups: The previously active `api_cost_multiplier/config.yaml` was backed up to `api_cost_multiplier/config.yaml.bak`. The provider registry files were edited in-place; please ensure version control (git) records these changes if you want to keep them.
- Rationale: These entries corresponded to failing runs in the "untested" test set and you requested they be removed from the registries.

Remaining registry models that were previously listed as "not tested" but are still present (and their observed status from the most recent test run)
- OpenAI
  - o1 — was observed as SUCCESS in the test run (report saved).
- Anthropic
  - claude-opus-4-1-20250805 — SUCCESS (report saved).
  - claude-3-7-sonnet-latest — SUCCESS (report saved).
  - claude-3-5-haiku-latest — SUCCESS (report saved).
  - claude-3-7-sonnet-20250219 — still present in registry; not exercised in the test run.
  - claude-3-5-haiku-20241022 — still present in registry; not exercised in the test run.

Other notes
- OpenRouter: `default` remains unchanged.
- MA allowlist (`api_cost_multiplier/model_registry/ma_supported.yaml`) was not modified.
- If you want these removed models restored later, provide the backups (or I can re-add them from upstream references if you prefer).

Suggested next steps (pick any you want me to perform)
- A) Commit these registry changes to git (I can prepare a commit message if you want).
- B) Produce a CSV mapping registry models -> tested (true/false) and save to `api_cost_multiplier/docs/registry_test_matrix.csv`.
- C) Restore any removed models from backups if you change your mind.
- D) Run the rerun-config for failing models before they were removed (not recommended since they're removed; would need re-adding to registry/config).
