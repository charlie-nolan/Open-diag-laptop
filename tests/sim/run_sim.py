#!/usr/bin/env python3
"""
v5: as v3/v4, plus: the verdict may be sent back once by the answer check (the LAST verdict is recorded, every
pass is in "calls"), and the step verdict's candidates/checks/ranking are logged ("steps"). Claude runs keep the
one-prompt verdict (config verdict_steps off), as the app does for API backends.
v3: same as v2 (single_car_v2/sim/run_sim.py), plus: the DATA CHECK block (app/sanity_check.py) and both passes of
the blind Final Diagnosis are logged ("calls": every model call with its prompt, output and counters).

Headless run of the deck's real Intake -> FINAL DIAGNOSIS (act_verdict) and one chat question (act_chat) per
scenario, in the real CyberdeckApp window (Qt offscreen), Home mode, with the app's own retrieval and prompts.
Nothing in app/ is edited: the harness only changes CFG in memory (kb_dir -> the car DB folder, a scratch session
DB/cache, voice off, no remote-manual hook) and wraps the model backend to record token counts.

  CYBERDECK_ROOT=~/open-diag-cyberdeck ~/open-diag-cyberdeck/venv/bin/python run_sim.py \
      --kb-dir ~/open-diag-cyberdeck/kb/cars/<car> --cases cases_set2_blind.json --run qwen --backend ollama --out results_qwen.jsonl
  --backend claude: the same prompts and system prompts to `claude -p --model claude-opus-5-5` (no tools).
"""
import argparse
import json
import os
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

import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = os.path.expanduser(os.environ.get("CYBERDECK_ROOT", "~/open-diag-cyberdeck"))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, os.path.join(ROOT, "kb"))

ap = argparse.ArgumentParser()
ap.add_argument("--kb-dir", required=True)
ap.add_argument("--run", required=True)
ap.add_argument("--backend", choices=["ollama", "claude", "hf"], default="ollama")
ap.add_argument("--hf-path", help="--backend hf: a local HF model folder or hub id (the deck's 4B, base or LoRA-merged)")
ap.add_argument("--claude-model", default="claude-opus-5-5")
ap.add_argument("--out", required=True)
ap.add_argument("--cases", default=os.path.join(HERE, "cases_set2_blind.json"))
ap.add_argument("--only", default="", help="comma list of case ids")
ap.add_argument("--no-chat", action="store_true")
ap.add_argument("--no-verdict", action="store_true", help="chat only (run verdicts first, then chats: fewer model swaps)")
ap.add_argument("--timeout", type=int, default=1800)
ap.add_argument("--deep-model", help="Ollama model for every role (e.g. the deck's 4B, base or LoRA)")
ap.add_argument("--ctx", type=int, help="home_context_len (the deck's RKLLM models have 4096)")
ap.add_argument("--think", action="store_true", help="THINK HARDER on: plain draft, then the thinking model reviews it")
ap.add_argument("--steps", choices=["auto", "on", "off"], default="auto", help="config verdict_steps for this run")
a = ap.parse_args()

import llm_backend  # noqa: E402
import qa_trace  # noqa: E402

scratch = os.path.join(HERE, "scratch", a.run)
os.makedirs(scratch, exist_ok=True)
qa_trace.DIR = os.path.join(scratch, "trace")
LAST = {}
CALLS = []


def ollama_generate(self, prompt, on_token, keep_history=False, max_new_tokens=None, temperature=None):
    import urllib.request
    msgs = [{"role": "system", "content": self.system_prompt}] if self.system_prompt else []
    msgs += self.history + [{"role": "user", "content": prompt}]
    payload = {"model": self.name, "messages": msgs, "stream": True, "think": self.think,
               "options": {"temperature": self.temperature if temperature is None else temperature,
                           "num_predict": max_new_tokens or self.max_new_tokens, "num_ctx": self.num_ctx,
                           **self.options}}
    req = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    parts, in_think, t0, final = [], False, time.time(), {}
    with llm_backend._RUN_LOCK:
        resp = urllib.request.urlopen(req, timeout=1800)
        for line in resp:
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("error"):
                raise RuntimeError(data["error"])
            msg = data.get("message", {})
            if msg.get("thinking"):
                t = ("<think>\n" if not in_think else "") + msg["thinking"]
                in_think = True
                parts.append(t)
                on_token(t)
            tok = msg.get("content", "")
            if tok and in_think:
                tok, in_think = "\n</think>\n\n" + tok, False
            if tok:
                parts.append(tok)
                on_token(tok)
            if data.get("done"):
                final = data
                break
        resp.close()
    text = "".join(parts)
    ev, ed = final.get("eval_count") or 0, (final.get("eval_duration") or 0) / 1e9
    LAST.update(model=self.name, system=self.system_prompt, prompt=prompt, wall_s=round(time.time() - t0, 1),
                prompt_tokens=final.get("prompt_eval_count"), output_tokens=ev,
                prompt_eval_s=round((final.get("prompt_eval_duration") or 0) / 1e9, 1), eval_s=round(ed, 1),
                tok_s=round(ev / ed, 1) if ed else None, load_s=round((final.get("load_duration") or 0) / 1e9, 1),
                num_ctx=self.num_ctx, num_predict=max_new_tokens or self.max_new_tokens,
                temperature=self.temperature if temperature is None else temperature, done_reason=final.get("done_reason"),
                text=text)
    CALLS.append(dict(LAST))
    return text


llm_backend.OllamaModel.generate = ollama_generate


class ClaudeModel:
    """The same system prompt and user prompt to claude -p (no tools, no settings, no session kept)."""

    def __init__(self, model, system):
        self.name, self.system_prompt, self.history = model, system, []

    def generate(self, prompt, on_token, keep_history=False, max_new_tokens=None, temperature=None):
        cmd = ["claude", "-p", "--model", self.name, "--system-prompt", self.system_prompt, "--tools", "",
               "--setting-sources", "", "--no-session-persistence", "--output-format", "json"]
        t0 = time.time()
        p = subprocess.run(cmd, input=prompt, capture_output=True, env=_claude_env(), text=True, timeout=a.timeout,
                           cwd=scratch)
        try:
            d = json.loads(p.stdout)
        except ValueError:
            raise RuntimeError(f"claude -p: {p.stdout[-300:]} {p.stderr[-300:]}")
        if d.get("is_error") or d.get("subtype") != "success":
            raise RuntimeError(f"claude -p: {d.get('subtype')} {str(d.get('result'))[:300]}")
        text = d.get("result", "")
        on_token(text)
        u = d.get("usage") or {}
        wall = time.time() - t0
        out_t = u.get("output_tokens") or 0
        LAST.update(model=self.name, system=self.system_prompt, prompt=prompt, wall_s=round(wall, 1),
                    prompt_tokens=(u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                    + (u.get("cache_creation_input_tokens") or 0), output_tokens=out_t,
                    eval_s=round((d.get("duration_api_ms") or wall * 1000) / 1000, 1),
                    tok_s=round(out_t / ((d.get("duration_api_ms") or wall * 1000) / 1000), 1) if out_t else None,
                    num_predict=max_new_tokens, temperature="CLI default (not settable)",
                    cost_usd_equiv=d.get("total_cost_usd"), usage=u, text=text)
        CALLS.append(dict(LAST))
        return text

    def clear_history(self):
        pass

    def abort(self):
        pass

    def release(self):
        pass


class HFModel:
    """--backend hf: the same prompts to a local transformers model (4-bit NF4 on the GPU: bitsandbytes 8-bit generation was too slow, no case finished in 1.5 h), greedy decoding (the app's
    verdict runs at temperature 0). Used to test the deck's 4B base vs LoRA without an Ollama import."""
    _cache = {}

    def __init__(self, path, system):
        self.name, self.system_prompt, self.history = path, system, []
        if path not in HFModel._cache:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            tok = AutoTokenizer.from_pretrained(path)
            m = AutoModelForCausalLM.from_pretrained(path, device_map={"": 0},
                                                     quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16))
            HFModel._cache[path] = (tok, m, torch)
        self.tok, self.m, self.torch = HFModel._cache[path]

    def generate(self, prompt, on_token, keep_history=False, max_new_tokens=None, temperature=None):
        msgs = ([{"role": "system", "content": self.system_prompt}] if self.system_prompt else []) + \
            [{"role": "user", "content": prompt}]
        enc = self.tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        ids = enc["input_ids"].to(0)
        room = max(256, (a.ctx or 4096) - ids.shape[1])
        t0 = time.time()
        with self.torch.no_grad():
            out = self.m.generate(ids, max_new_tokens=min(room, max_new_tokens or 2200), do_sample=False)
        text = self.tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True)
        on_token(text)
        n = out.shape[1] - ids.shape[1]
        LAST.update(model=self.name, system=self.system_prompt, prompt=prompt, wall_s=round(time.time() - t0, 1),
                    prompt_tokens=int(ids.shape[1]), output_tokens=int(n),
                    tok_s=round(n / max(0.1, time.time() - t0), 1), text=text)
        CALLS.append(dict(LAST))
        return text

    def clear_history(self):
        pass

    def abort(self):
        pass

    def release(self):
        pass


import cyberdeck_gui as G  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
import faithfulness  # noqa: E402

G.CFG.update(home=True, home_url="http://127.0.0.1:11434", kb_dir=os.path.abspath(a.kb_dir),
             session_db=os.path.join(scratch, "session.db"), cache_dir=os.path.join(scratch, "cache"),
             voice_enabled=False)
os.makedirs(G.CFG["cache_dir"], exist_ok=True)
if a.backend == "hf":
    G.ModelManager._pc_model = lambda self, role: HFModel(a.hf_path, G.FAST_SYSTEM if role == "fast" else G.DEEP_SYSTEM)
if a.backend == "claude":
    G.CFG["verdict_steps"] = False
    G.ModelManager._pc_model = lambda self, role: ClaudeModel(
        a.claude_model, G.FAST_SYSTEM if role == "fast" else G.DEEP_SYSTEM)
    for r in ("fast", "deep", "think"):
        G.CFG[f"home_{r}"] = a.claude_model

cases = json.load(open(a.cases))
car = cases["car"]
todo = [c for c in cases["cases"] if not a.only or str(c["id"]) in a.only.split(",")]
done_ids = set()
if os.path.isfile(a.out):
    for ln in open(a.out):
        try:
            r = json.loads(ln)
            if not r.get("error"):
                done_ids.add((r["case"], r["kind"]))
        except ValueError:
            pass

app = QApplication(sys.argv)
s0 = G.Session(G.CFG["session_db"])
s0.set("vehicle_info", json.dumps({"year": str(car["year"]), "make": car["make"], "model": car["model"]}))
if a.deep_model:
    for r_ in ("fast", "deep", "think"):
        G.CFG[f"home_{r_}"] = a.deep_model
if a.ctx:
    G.CFG["home_context_len"] = a.ctx
if a.steps != "auto":
    G.CFG["verdict_steps"] = a.steps == "on"
win = G.CyberdeckApp()
if a.think:
    win.chk_think.setChecked(True)
print(f"kb: {G.CFG['kb_db']} | retriever {type(win.retriever).__name__} | {win.kb_msg}", flush=True)


def wait(pred, limit):
    t0 = time.time()
    while not pred():
        app.processEvents()
        time.sleep(0.05)
        if time.time() - t0 > limit:
            return False
    for _ in range(20):
        app.processEvents()
    return True


def busy():
    return any(w.isRunning() for w in getattr(win, "lookups", [])) or (win.worker is not None and win.worker.isRunning())


def hits_of(prompt):
    try:
        return [(lbl[:90] + " | " + (txt or "").strip().split("\n")[0][:90]) for lbl, txt in faithfulness.pages(prompt)][1:]
    except Exception as e:
        return [f"(pages() failed: {e})"]


def record(case, kind, text, t0, err=None, extra=None):
    rec = {"case": case["id"], "kind": kind, "run": a.run, "backend": a.backend, "kb_dir": a.kb_dir, **(extra or {}),
           "model": LAST.get("model"), "wall_s_total": round(time.time() - t0, 1), "error": err,
           "retrieval_hits": hits_of(LAST.get("prompt", "")), "prompt_chars": len(LAST.get("prompt", "")),
           **{k: v for k, v in LAST.items() if k not in ("prompt", "system", "text")},
           "prompt": LAST.get("prompt"), "output": text}
    try:
        rec["source_check"] = faithfulness.report(text, LAST.get("prompt", "")) if text and not err else ""
    except Exception as e:
        rec["source_check"] = f"failed: {e}"
    with open(a.out, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"case {case['id']:>2} {kind:7s} {rec['wall_s_total']:7.1f} s  in {rec.get('prompt_tokens')} out "
          f"{rec.get('output_tokens')} tok/s {rec.get('tok_s')} {'ERROR ' + str(err) if err else ''}", flush=True)


for case in todo:
    win._clear_case()
    s = win.session
    s.set("vehicle_info", json.dumps({"year": str(car["year"]), "make": car["make"], "model": car["model"],
                                      "trans": "", "miles": "", "vin": "", "engine": "", "customer": ""}))
    for k in ("dtcs", "telemetry", "symptoms", "ruled_out", "suspect", "history"):
        s.set(k, "" if case.get(k) in (None, "(none)") else case[k])
    s.set("intake_note", f"Conditions: {case['conditions']}" if case.get("conditions") else "")
    win._load_case()
    win._store_case()
    win.chat_started = False
    win.txt_notes.setPlainText("")
    data_check = win._data_check()
    if not a.no_verdict and (case["id"], "verdict") not in done_ids:
        LAST.clear()
        CALLS.clear()
        got = {}
        orig = win._verdict_done

        def vd(text, o=orig):
            got["text"] = text
            got["n"] = got.get("n", 0) + 1
            o(text)
        win._verdict_done = vd
        if a.backend == "claude":
            win._think_done = win._verdict_done
        t0 = time.time()
        err = None
        try:
            win.act_verdict()
            def finished():
                if "[LLM error" in (LAST.get("text") or "") and not busy():
                    return True
                if "text" not in got or busy():
                    return False
                return not (getattr(win, "_verdict_retried", False) and got.get("n", 0) < 2)
            ok = wait(finished, a.timeout)
            if not ok:
                err = "timeout"
                win.act_stop()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        text = got.get("text") or LAST.get("text") or win.txt_verdict.toPlainText()
        if "[LLM error" in (text or ""):
            err = err or text.strip()[-300:]
        win._verdict_done = orig
        calls = [{k: v for k, v in c.items() if k != "system"} for c in CALLS]
        record(case, "verdict", text, t0, err, {
            "data_check": data_check, "blind": len(calls) > 1, "pass1_output": getattr(win, "_blind_pass1", ""),
            "pass1_prompt": calls[0]["prompt"] if len(calls) > 1 else "", "calls": [
                {k: v for k, v in c.items() if k not in ("prompt", "text")} for c in calls],
            "wall_s_by_pass": [c.get("wall_s") for c in calls], "retried": bool(getattr(win, "_verdict_retried", False)),
            "steps": [list(x) for x in getattr(win, "_steps_log", [])], "verdict_calls": got.get("n", 0)})
        win._steps_log = []
    if not a.no_chat and case.get("chat") and (case["id"], "chat") not in done_ids:
        LAST.clear()
        CALLS.clear()
        win.txt_chat.clear()
        win.in_chat.setText(case["chat"])
        t0 = time.time()
        err = None
        before = win.worker
        try:
            win.act_chat()
            ok = wait(lambda: win.worker is not before and win.worker is not None and not busy(), a.timeout)
            if not ok:
                err = "timeout"
                win.act_stop()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        text = LAST.get("text") or win.txt_chat.toPlainText()
        if "[LLM error" in text:
            err = err or text.strip()[-300:]
        record(case, "chat", text, t0, err, {"data_check": data_check})
print("sim done", flush=True)
os._exit(0)
