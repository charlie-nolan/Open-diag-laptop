#!/usr/bin/env python3
"""Blind grading of Final Diagnosis answers: for each case, the answers of every run are shuffled and labelled A, B,
C... and sent with the case and its `expected` note to a fresh `claude -p` (no tools, no session). The grader never
sees which model, DB or run wrote an answer. Scores: 2 = right direction, 1 = plausible but leads with a guess,
skips the cheaper check, or stops for more data when the case had enough, 0 = wrong lead.

  blind_grade.py --scenarios sim/scenarios.json --out grades_blind.json run_name=results.jsonl [run_name=...]
"""
import argparse
import json
import os
import random
import re
import subprocess

def _claude_env():
    """Environment for `claude -p`: the long-lived token from ~/.config/claude_oauth_token when it exists (made with
    `claude setup-token`), so unattended runs don't stop when the normal login expires. The value is never printed."""
    import os as _os
    env = dict(_os.environ)
    p = _os.path.expanduser("~/.config/claude_oauth_token")
    if _os.path.isfile(p):
        tok = open(p).read().strip()
        if tok.startswith("sk-ant-") and " " not in tok:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    return env


ap = argparse.ArgumentParser()
ap.add_argument("--scenarios", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--model", default="claude-opus-5-5")
ap.add_argument("--seed", type=int, default=20261113)
ap.add_argument("runs", nargs="+")
a = ap.parse_args()

_sc = json.load(open(a.scenarios))
cases = {c["id"]: c for c in _sc["cases"]}
CAR = " ".join(str(_sc.get("car", {}).get(k, "")) for k in ("year", "make", "model", "engine")).strip()
answers = {}
for spec in a.runs:
    name, path = spec.split("=", 1)
    for ln in open(path):
        r = json.loads(ln)
        if r["kind"] == "verdict" and not r.get("error"):
            answers.setdefault(r["case"], {})[name] = re.sub(r"(?s)<think>.*?</think>", "", r["output"] or "").strip()

RUBRIC = ("Score each answer 0, 1 or 2 against the EXPECTED note (the grader's key; the answers never saw it):\n"
          "2 = right direction: its first issue (or its first step, if it stops to ask for data) matches the expected "
          "likeliest cause or an acceptable alternative, or, where the case's data really is impossible or too thin, "
          "it says so and asks for the right tests.\n"
          "1 = plausible but leads with someone's guess, skips the cheaper check the key puts first, has the right "
          "cause only lower down, or stops to ask for more data when the case already had enough.\n"
          "0 = wrong lead, or diagnoses data the key says is impossible.\n"
          "Judge the content only, not the writing style or length. Answers are in random order.")
out = {"model": a.model, "seed": a.seed, "grades": {}, "reasons": {}}
if os.path.isfile(a.out):
    out = json.load(open(a.out))
rng = random.Random(a.seed)
for cid in sorted(answers):
    if str(cid) in out["grades"]:
        continue
    c = cases[cid]
    names = sorted(answers[cid])
    rng.shuffle(names)
    labels = {chr(65 + i): n for i, n in enumerate(names)}
    case_txt = "\n".join(f"{k}: {c.get(k)}" for k in ("dtcs", "symptoms", "telemetry", "history", "ruled_out",
                                                       "suspect", "conditions"))
    prompt = (f"CAR: {CAR}.\nCASE:\n{case_txt}\n\nEXPECTED (grading key):\n"
              f"{c['expected']}\n\n{RUBRIC}\n\n"
              + "\n\n".join(f"=== ANSWER {L} ===\n{answers[cid][n][:6000]}" for L, n in labels.items())
              + '\n\nReply with only JSON: {"A": {"score": 0|1|2, "reason": "<one sentence>"}, ...} for every answer.')
    p = subprocess.run(["claude", "-p", "--model", a.model, "--tools", "", "--setting-sources", "",
                        "--no-session-persistence", "--output-format", "json"], input=prompt, capture_output=True, env=_claude_env(),
                       text=True, timeout=900, cwd=os.path.dirname(os.path.abspath(a.out)))
    try:
        d = json.loads(p.stdout)
        res = d.get("result") or ""
        if d.get("is_error"):
            raise SystemExit(f"grader call failed: {res[:300]}")
        g = json.loads(re.search(r"\{.*\}", res, re.S).group(0))
    except (ValueError, AttributeError, KeyError) as e:
        print(f"case {cid}: grader output unreadable ({e}): {p.stdout[-200:]}", flush=True)
        continue
    out["grades"][str(cid)] = {labels[L]: v.get("score") for L, v in g.items() if L in labels}
    out["reasons"][str(cid)] = {labels[L]: v.get("reason") for L, v in g.items() if L in labels}
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"case {cid}: " + ", ".join(f"{n} {out['grades'][str(cid)].get(n)}" for n in sorted(answers[cid])), flush=True)
tot = {}
for cid, g in out["grades"].items():
    for n, s in g.items():
        tot[n] = tot.get(n, 0) + (s or 0)
out["totals"] = tot
json.dump(out, open(a.out, "w"), indent=1)
print("totals:", tot)
