"""One function, ask_json(), over a chain of LLM providers.

Providers are tried in the order listed in config.yaml. A provider that fails
(subscription limit, rate limit, offline, bad key) is skipped for a cooldown
period and the next one is used, so the studio keeps running when the Claude
subscription runs out.
"""
import json
import logging
import re
import subprocess
import tempfile
import time

import httpx

from . import db
from .config import cfg, secrets

log = logging.getLogger("thoma.llm")


class AllProvidersFailed(RuntimeError):
    pass


last_provider = None  # name of the provider that answered the last ask_json() (recorded on scripts)


def _chain(task: str) -> list[dict]:
    """Providers for this job, in order. config llm.roles maps a job (write, review, research, triage)
    to provider names, e.g. Qoder writes and Claude checks; without roles every job uses llm.providers."""
    conf = cfg()["llm"]
    role = {"revise": "write"}.get(task.split("-")[0], task.split("-")[0])
    names = (conf.get("roles") or {}).get(role)
    by_name = {p["name"]: p for p in conf["providers"]}
    chain = [by_name[n] for n in names if n in by_name] if names else conf["providers"]
    # Owner (2026-10-29, again 2026-10-30): never Opus, whatever the config says. It writes too technically.
    return [p for p in chain if "opus" not in json.dumps(p).lower()]


def _claude_cli(p: dict, system: str, prompt: str) -> str:
    cmd = ["claude", "-p", "--output-format", "json", "--model", p.get("model") or "sonnet",
           "--system-prompt", system, "--tools", "", "--no-session-persistence",
           "--setting-sources", ""]
    # Run from an empty folder so no project CLAUDE.md or MCP config leaks in.
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600, cwd=tmp)
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude exit {r.returncode}: {(r.stderr or r.stdout)[:300]}")
    if out.get("is_error") or r.returncode != 0:
        raise RuntimeError(f"claude: {str(out.get('result'))[:300]}")
    return out["result"]


OUT_OF_CREDITS = re.compile(r"credits? (have been )?exhausted|credit usage limit|upgrade your subscription", re.I)


def _cli(p: dict, system: str, prompt: str) -> str:
    """Any agent CLI in print mode (e.g. `qodercli -p`): prompt on stdin, answer on stdout."""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(p["command"], input=f"{system}\n\n---\n\n{prompt}", capture_output=True,
                           text=True, timeout=900, cwd=tmp)
    if r.returncode != 0 or not r.stdout.strip() or (OUT_OF_CREDITS.search(r.stdout) and "{" not in r.stdout):
        raise RuntimeError(f"{p['command'][0]} exit {r.returncode}: {(r.stderr or r.stdout)[:300]}")
    return r.stdout


def _gemini(p: dict, system: str, prompt: str) -> str:
    """Gemini through an AI Studio key (free tier). Tries each model with each key: every pair has its
    own daily quota. Pro models have no free quota, so config lists Flash models."""
    errors = []
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
    for model in p["models"]:
        for key in secrets(p.get("api_key_env", "GEMINI_API_KEY")):
            try:
                r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                               json=body, headers={"x-goog-api-key": key}, timeout=300)
            except httpx.HTTPError as e:
                errors.append(f"{model}: {type(e).__name__}")
                continue
            if r.status_code == 200:
                parts = r.json()["candidates"][0]["content"].get("parts", [])
                text = "".join(x.get("text", "") for x in parts if not x.get("thought"))
                if text.strip():
                    return text
            errors.append(f"{model}: HTTP {r.status_code}")
            if r.status_code not in (200, 401, 403, 404, 429, 500, 503):
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    raise RuntimeError("no Gemini model answered: " + "; ".join(errors[-4:]))


def _openai(p: dict, system: str, prompt: str) -> str:
    keys = secrets(p["api_key_env"]) if p.get("api_key_env") else ["none"]
    if not keys:
        raise RuntimeError(f"{p['api_key_env']} is not set")
    body = {
        "model": p["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
    }
    for key in keys:  # backup keys take over when one is rate-limited or rejected
        r = httpx.post(f"{p['base_url'].rstrip('/')}/chat/completions", json=body, timeout=300,
                       headers={"Authorization": f"Bearer {key}"})
        if r.status_code not in (401, 403, 429):
            break
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


CALLERS = {"claude_cli": _claude_cli, "cli": _cli, "openai": _openai, "gemini": _gemini}


def parse_json(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def ask_json(system: str, prompt: str, task: str = "") -> dict:
    """Send a prompt, get a parsed JSON object back. Raises AllProvidersFailed."""
    conf = cfg()["llm"]
    cooldown = conf.get("cooldown_minutes", 60) * 60
    benched = db.get_kv("llm_benched", {})
    global last_provider
    errors = []
    for p in _chain(task):
        if time.time() < benched.get(p["name"], 0):
            continue
        for attempt in range(2):
            t0 = time.time()
            try:
                text = CALLERS[p["type"]](p, system, prompt)
                result = parse_json(text)
                if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
                    result = result[0]  # some models wrap the object in a list
                if not isinstance(result, dict):
                    raise json.JSONDecodeError("not a JSON object", text[:50], 0)
                log.info("llm %s ok (%s, %.0fs)", p["name"], task, time.time() - t0)
                last_provider = p["name"]
                return result
            except json.JSONDecodeError:
                errors.append(f"{p['name']}: reply was not JSON")
                prompt += "\n\nReply with ONE valid JSON object only. No prose, no code fences."
            except Exception as e:  # provider down, limit hit, timeout
                errors.append(f"{p['name']}: {e}")
                log.warning("llm %s failed (%s): %s", p["name"], task, e)
                benched[p["name"]] = time.time() + cooldown
                db.set_kv("llm_benched", benched)
                break
    raise AllProvidersFailed("; ".join(errors) or "every provider is cooling down")
