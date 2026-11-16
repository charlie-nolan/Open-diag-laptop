# Simulation harness and blind grader

- `run_sim.py` runs each case through the real app: it opens the app's window off-screen, fills in Intake, presses
  FINAL DIAGNOSIS (and one chat question), and logs the prompt, the answer, the DATA CHECK, both blind passes, the
  timings and the token counts. Backends: `ollama` (any Ollama model, with `--deep-model`), `claude` (`claude -p`),
  `hf` (a local transformers model, e.g. the deck's 4B). Set `CYBERDECK_ROOT` to your open-diag-cyberdeck folder.
- `blind_grade.py` shuffles every run's answers per case, labels them A, B, C..., and has a fresh `claude -p` score
  each one 0-2 against the case's key, without knowing which run wrote which.
- `cases_set1.json` and `cases_set2_blind.json` hold the 20 + 20 cases (test data only: never shown to the models'
  prompts, except their intake fields). `grades/` holds the blind grades behind docs/TEST_RESULTS.md.

The raw answers aren't included, because they quote copyrighted manual pages. Run the harness against your own
database to get your own.
