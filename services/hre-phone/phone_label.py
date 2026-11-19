#!/usr/bin/env python3
"""Recall-first labeller for HRE T1: one owner message -> {flag, p_flag, cue, concepts, ask}.
Talks to a llama-server (/v1/chat/completions, json_schema grammar, logprobs for the flag).
Resumable: skips ids already present in --out. Owner text only ever goes to --url (local/phone).
Usage: phone_label.py --url http://host:8080 [--key-file F] --in shard.jsonl --out labels.jsonl
       [--mode full|flag] [--max-chars 6000] [--model-tag NAME]"""
import argparse, json, math, os, sys, time, urllib.request

SYS_FULL = (
    "You label messages a user (Kevin) typed to an AI coding agent. Return JSON only.\n"
    "flag: \"y\" if the message corrects the agent, repeats or re-explains something already asked, "
    "or complains/expresses frustration (e.g. 'I already told you', 'again', 'still', 'wtf', "
    "'not what I asked', 'check memory', 'we did this before', 'why didn't you', 'no, I meant'). "
    "When unsure, answer \"y\". Otherwise \"n\".\n"
    "cue: the exact short phrase from the message that made you flag it, else \"\".\n"
    "concepts: specific named things in the message (repos, projects, machines/devices, bots/profiles, "
    "skills, tools, products, libraries, models, features), lowercase, at most 8. No generic words.\n"
    "ask: what he wants done, imperative, at most 15 words; \"\" if no request.")
SYS_FLAG = (
    "You judge one message a user (Kevin) typed to an AI agent. Return JSON only.\n"
    "flag: \"y\" if it corrects the agent, repeats or re-explains something already asked, or complains/"
    "expresses frustration ('I already told you', 'again', 'still', 'wtf', 'not what I asked', "
    "'check memory', 'we did this before', 'why didn't you', 'no, I meant'). When unsure, \"y\". Else \"n\".\n"
    "cue: the exact short phrase that made you flag it, else \"\".")
SCHEMA_FULL = {"type": "object", "properties": {
    "flag": {"type": "string", "enum": ["y", "n"]}, "cue": {"type": "string", "maxLength": 80},
    "concepts": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 8},
    "ask": {"type": "string", "maxLength": 120}}, "required": ["flag", "cue", "concepts", "ask"]}
SCHEMA_FLAG = {"type": "object", "properties": {
    "flag": {"type": "string", "enum": ["y", "n"]}, "cue": {"type": "string", "maxLength": 80}},
    "required": ["flag", "cue"]}


def call(url, key, body, timeout):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(), h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def p_yes(resp):
    """P(flag=y) from the logprobs of the token that carries the flag value."""
    try:
        toks = resp["choices"][0]["logprobs"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    text = ""
    for t in toks:
        before = text
        text += t["token"]
        if '"flag"' in before and before.rstrip().endswith('"') and t["token"].strip('" ') in ("y", "n"):
            py = pn = 0.0
            for alt in t.get("top_logprobs", []):
                s = alt["token"].strip('" ')
                if s == "y":
                    py += math.exp(alt["logprob"])
                elif s == "n":
                    pn += math.exp(alt["logprob"])
            return round(py / (py + pn), 4) if py + pn > 0 else None
    return None


D1_QUESTIONS = {
    "flag": {"type": "noul", "instructions":
             "Does the user correct the agent, repeat or re-explain something he already asked, "
             "or complain / express frustration about the agent?"},
    "kind": {"type": "choice", "instructions": "Which best describes the message?",
             "criteria": {"correction": "Corrects the agent or says it got something wrong",
                          "repeat": "Repeats or re-explains an earlier ask or fact",
                          "complaint": "Complains or expresses frustration",
                          "none": "A new request, question or neutral statement"}}}


def label_d1(url, key, text, timeout):
    """Liquid d1 decision model: one forward pass, calibrated P(yes) via /v1/systemone."""
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    t0 = time.time()
    req = urllib.request.Request(url + "/v1/systemone",
                                 json.dumps({"state": text, "questions": D1_QUESTIONS}).encode(), h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    a = resp["answers"]
    p = a["flag"]["noul"]
    return {"flag": "y" if p >= 0.5 else "n", "p_flag": round(p, 4), "cue": "",
            "kind": a["kind"]["choice"], "kind_p": {k: round(v, 3) for k, v in a["kind"]["probabilities"].items()},
            "_ms": int((time.time() - t0) * 1000), "_tok": [resp.get("usage", {}).get("input_tokens"), 0]}


def label(url, key, text, mode, max_chars, timeout=600):
    if len(text) > max_chars:   # keep head and tail; owner intent is usually at either end
        text = text[: max_chars * 2 // 3] + "\n...\n" + text[-max_chars // 3:]
    if mode == "d1":
        return label_d1(url, key, text, timeout)
    body = {"messages": [{"role": "system", "content": SYS_FULL if mode == "full" else SYS_FLAG},
                         {"role": "user", "content": "Message:\n<<<\n" + text + "\n>>>"}],
            "temperature": 0, "max_tokens": 220 if mode == "full" else 60,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "label", "schema": SCHEMA_FULL if mode == "full" else SCHEMA_FLAG}},
            "logprobs": True, "top_logprobs": 5,
            "chat_template_kwargs": {"enable_thinking": False}}
    t0 = time.time()
    resp = call(url, key, body, timeout)
    out = json.loads(resp["choices"][0]["message"]["content"])
    out["p_flag"] = p_yes(resp)
    u = resp.get("usage", {})
    out["_ms"] = int((time.time() - t0) * 1000)
    out["_tok"] = [u.get("prompt_tokens"), u.get("completion_tokens")]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--key-file")
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["full", "flag", "d1"], default="full")
    ap.add_argument("--max-chars", type=int, default=6000)
    ap.add_argument("--model-tag", default="")
    ap.add_argument("--worker", default=os.environ.get("HOSTNAME", ""))
    a = ap.parse_args()
    key = open(a.key_file).read().strip() if a.key_file else ""
    done = set()
    if os.path.exists(a.out):
        for l in open(a.out):
            try:
                done.add(json.loads(l)["id"])
            except Exception:
                pass
    n = err = 0
    with open(a.out, "a") as fo:
        for l in open(a.inp):
            r = json.loads(l)
            if r["id"] in done:
                continue
            for attempt in range(3):
                try:
                    o = label(a.url, key, r["text"], a.mode, a.max_chars)
                    break
                except Exception as e:  # noqa: BLE001 - retry transport/JSON errors, then record
                    o = {"error": f"{type(e).__name__}: {e}"[:200]}
                    time.sleep(5 * (attempt + 1))
            if "error" in o:
                err += 1
                print(json.dumps({"id": r["id"], **o}), file=sys.stderr, flush=True)
                continue
            fo.write(json.dumps({"id": r["id"], "model": a.model_tag, "mode": a.mode, "worker": a.worker,
                                 "ts": round(time.time(), 1), **o}, ensure_ascii=False) + "\n")
            fo.flush()
            n += 1
    print(json.dumps({"labelled": n, "errors": err, "skipped_done": len(done)}), flush=True)
    sys.exit(1 if err and not n else 0)


if __name__ == "__main__":
    main()
