# Test results: what we tested, how, and what helped

These are simulated diagnoses, not repairs on real cars. Every number below comes from the harness and grader in
[`tests/sim/`](../tests/sim/), on one test car: a 2002 Subaru Forester (EJ251 2.5 L SOHC). They tell you how the
app's diagnosis behaves with different models and settings. They don't prove that it works on your car.

## The setup

- **Two databases for the same car**, both built with `tools/build_car_db.sh`:
  - **factory**: the factory service manual PDF plus the LEMON Manuals download.
  - **LEMON**: the LEMON download only.
- **Two test sets of 20 intake cases each.** Each case has codes, live data, symptoms, history, someone's guess
  and a grading key.
  - **set 1**: written while the app was being developed.
  - **set 2 (blind)**: written by a fresh Claude call that never saw the app, the fixes or set 1. It includes a
    manual-transmission-only fault and an impossible-data case.
- **Models:**
  - **Qwen3-Next 80B** (local, Ollama on an RTX 3070 PC).
  - **Claude Opus 5.5** (via `claude -p`).
  - **the Orange Pi deck's Qwen3-4B**, stock and fine-tuned (LoRA). The 4B was run through transformers at 4-bit
    with the deck's 4096-token context.
- **Each case is run through the real app.** The harness opens the app's window off-screen, fills in Intake, and
  presses FINAL DIAGNOSIS, so the prompts and manual lookups are the app's own.

## How it was graded

- **Blind:** for each case, the answers from every run are shuffled and labelled A, B, C. A fresh `claude -p` scores
  them against the case's key without knowing which model or setting wrote which:
  - **2** = right direction.
  - **1** = plausible, but it leads with someone's guess, skips the cheaper check, or stops for data it already had.
  - **0** = wrong lead, or it diagnosed data that was impossible.
  - The maximum is 40 per set.
- **Caveat 1:** the grader is also Claude, and the writing style might give Claude's answers away.
- **Caveat 2: grader noise.** Re-grading the same answers on another day moved a total by about 3 points, so
  differences of 3 or less mean little.
- **Caveat 3:** early on, the developer (Claude) graded by hand. Those grades were kinder to Qwen than the blind
  grader by 2-4 points, and are not used here.

## Results

### What the app does around the model (set 1, blind grades)

The same 20 cases after each round of changes:
- **v3:** data check + blind first pass + vision text.
- **round 3:** a guess only moves up with evidence, and picture charts lead only for their own code.
- **v4:** NEEDS MORE DATA, tie-break, answer check, temperature 0.

| run | v3 | round 3 | v4 |
|---|---|---|---|
| Qwen 80B, factory DB | 25 | 25 | 29 |
| Qwen 80B, LEMON DB | 25 | 25 | 25 |
| Claude, factory DB | 38 | 40 | 39 |
| Claude, LEMON DB | 38 | 39 | 40 |

### Never-seen cases (set 2, blind, v4)

| run | score |
|---|---|
| Qwen 80B, factory DB | 27 |
| Qwen 80B, LEMON DB | 28 |
| Claude, factory DB | 39 |
| Claude, LEMON DB | 40 |

- **Manual-only fault:** Claude 2/2, Qwen 1/1.
- **Impossible data:** Claude stopped and asked for a rescan (2/2). Qwen diagnosed it anyway (1/1). The app now stops
  in Python instead (see below).

### Ways of getting Qwen 80B to do better (factory DB, blind, set 2 / set 1)

| verdict style | set 2 | set 1 | time per verdict |
|---|---|---|---|
| one prompt (the default) | 30 | 32 | ~200-250 s |
| step by step (model lists causes, checks each, Python ranks) | 25 | 25 | ~430-480 s |
| THINK HARDER (draft, then the thinking 80B reviews it) | 29 | 30 | ~500 s |

The one-prompt verdict stays the default. Step mode is still in the app (`"verdict_steps": true`), but it's off.

### The deck's 4B, stock vs fine-tuned (set 2, never in the training data)

| 4B | score | plans in the app's format | time |
|---|---|---|---|
| stock | 19 | 19/20 | 33 s |
| LoRA, 209 good answers from set 1 + 400 card examples | 21 | 16/20 | 73 s |

The +2 is inside the grader's noise, and the LoRA wrote 2.4x more text, so it was not shipped. For Final Diagnosis,
the deck does best sending the job to a bigger model on the desktop when one is reachable.

### Factory PDF vs LEMON only (same car)

| | factory + LEMON | LEMON only | LEMON + vision step |
|---|---|---|---|
| walkable diagnostic trees | 74 | 0 | **92** |
| torque/spec rows | 454 | 14 | **87** |
| build time (GPU embedding, inputs ready) | 213 s | 136 s | + ~1.75 h of vision reading |

- The vision step reads chart and spec-table pictures at about 11 s per picture on an RTX 3070. Everything it reads
  is marked unverified in the app.
- In the sims, the database changed a model's lead in only a few cases. The model mattered far more than the manual
  source.

## What helped and what didn't

**Helped:**
- **Python checks the model can't skip:**
  - The **data check** flags impossible readings, bad codes, and parts the car doesn't have.
  - The **hard stop** writes NEEDS MORE DATA itself when the flagged readings are the ones a diagnosis would rest on.
  - The **answer check** flags an issue 1 that blames a part the case says was verified good or just replaced.
  - These took Qwen from diagnosing impossible data (0) to stopping correctly (2).
- **Blind first pass:** the Suspect field and earlier guesses are hidden from the first pass. That fixed cases where
  a guess steered the model (a click-no-start blamed on the ignition switch, a ball joint blamed after a pothole).
- **Neutral card wording:** "most often reported fix" instead of "#1 confirmed fix". Qwen stopped leading with a
  card's top fix over the manual.
- **A stronger model:** Claude scored 37-40 throughout, the 80B 25-32, the 4B about 20. With the `cli` backend, a
  laptop with no GPU can use a Claude, ChatGPT/Codex or Gemini subscription for the diagnosis.

**Didn't help:**
- step-by-step verdicts
- the thinking-model reviewer
- fine-tuning the 4B on ~200 examples
- making the first issue a test instead of a cause (Charlie's call: answers stay a differential)

## What is not published

The raw model answers and prompts are not published: they quote the service manual pages, which are copyrighted.
Only the cases, the grades (with the grader's one-line reasons), the harness and the grader are here.
