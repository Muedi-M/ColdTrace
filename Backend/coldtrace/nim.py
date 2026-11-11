"""NVIDIA NIM (OpenAI-compatible) client. Uses plain `requests`: no SDK dependency.

Key handling: NVIDIA_API_KEY env var, or Google Secret Manager when NIM_SECRET_NAME is set
(projects/<p>/secrets/<s>/versions/latest). The key is never logged or placed in exception text.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

import requests

from .features import LABELS

BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
# IDs listed as free endpoints on build.nvidia.com (checked 2026-11-10). Capabilities are inferred from
# names only: confirm with NimClient.list_models() and the comparison script. First entry = recommended default.
# Per-model request fields. Thinking-on is the default for these and burns the token budget before the answer
# (finish=length). enable_thinking=false is documented on the lightning page; ultra uses the same template
# key but its page only shows True, so verify with compare_nim.py. Env NIM_EXTRA_BODY still overrides.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}
MODEL_EXTRA = {
    "nvidia/nemotron-3.5-lightning-30b-a3b": NO_THINK,
    "nvidia/nemotron-3-ultra-550b-a55b": NO_THINK,
}
# Reasoning models with no documented off switch: need large max_tokens (NIM_CLASSIFY_MAX_TOKENS=4096) and a long NIM_TIMEOUT.
CANDIDATES = ["z-ai/glm-5.3-flash", "minimaxai/minimax-m3.1-flash", "mistralai/mistral-large-4-1t-a52b"]

DEFAULT_MODELS = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-3-ultra-550b-a55b",
]  # deepseek-ai/deepseek-v4.1-flash dropped: ReadTimeout on every call from the team network


def get_api_key() -> str:
    key = os.getenv("NVIDIA_API_KEY")
    if key:
        return key
    secret = os.getenv("NIM_SECRET_NAME")
    if secret:
        from google.cloud import secretmanager  # lazy: only needed on GCP

        resp = secretmanager.SecretManagerServiceClient().access_secret_version(name=secret)
        return resp.payload.data.decode().strip()
    raise RuntimeError("NVIDIA_API_KEY not set and NIM_SECRET_NAME not configured")


def env_var_for(model: str) -> str:
    """nvidia/llama-3.3-nemotron-super-49b-v1 -> NVIDIA_API_KEY_NVIDIA_LLAMA_3_3_NEMOTRON_SUPER_49B_V1"""
    return "NVIDIA_API_KEY_" + re.sub(r"[^A-Za-z0-9]+", "_", model).strip("_").upper()


def load_key_map() -> dict[str, str]:
    """Per-model keys as {model_id: key}. Sources, later wins: the JSON file at $NVIDIA_KEYS_FILE
    (default ./.nim_keys.json), then the JSON string in $NVIDIA_API_KEYS. A "default" entry covers
    any model without its own key."""
    out: dict = {}
    try:
        path = os.getenv("NVIDIA_KEYS_FILE", ".nim_keys.json")
        if os.path.isfile(path):
            with open(path) as f:
                out.update(json.load(f))
        raw = os.getenv("NVIDIA_API_KEYS")
        if raw:
            out.update(json.loads(raw))
    except (ValueError, OSError):
        raise RuntimeError("could not read per-model keys: check the JSON in .nim_keys.json / NVIDIA_API_KEYS") from None
    return {k: v for k, v in out.items() if isinstance(k, str) and isinstance(v, str) and v}


class NimError(RuntimeError):
    pass


@dataclass
class NimResult:
    text: str
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 1
    finish: str = ""


@dataclass
class NimClient:
    api_key: str | None = field(default=None, repr=False)  # default key; resolved lazily if None
    keys: dict = field(default_factory=load_key_map, repr=False)  # per-model overrides
    base_url: str = BASE_URL
    timeout: float = float(os.getenv("NIM_TIMEOUT", "120"))
    max_retries: int = int(os.getenv("NIM_MAX_RETRIES", "6"))
    session: requests.Session = field(default_factory=requests.Session, repr=False)

    def key_for(self, model: str | None = None) -> str:
        """Order: keys map / file entry for this model, env var for this model, explicit default,
        "default" map entry, NVIDIA_API_KEY / Secret Manager. Never echoes a key in errors."""
        if model:
            k = self.keys.get(model) or os.getenv(env_var_for(model))
            if k:
                return k
        k = self.api_key or self.keys.get("default")
        if k:
            return k
        try:
            return get_api_key()
        except RuntimeError:
            raise RuntimeError(f"no API key for {model or 'default'}: add it to .nim_keys.json, "
                               f"set {env_var_for(model) if model else 'NVIDIA_API_KEY'}, or set NVIDIA_API_KEY") from None

    def _headers(self, model: str | None = None) -> dict:
        return {"Authorization": f"Bearer {self.key_for(model)}", "Accept": "application/json"}

    def list_models(self) -> list[str]:
        r = self.session.get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
        if r.status_code != 200:
            raise NimError(f"list_models HTTP {r.status_code}")
        return sorted(m["id"] for m in r.json().get("data", []))

    def chat(self, model: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 300,
             extra: dict | None = None) -> NimResult:
        body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        body.update(MODEL_EXTRA.get(model, {}))
        body.update(_extra_body())
        if extra:
            body.update(extra)
        key = self.key_for(model)
        last = "unknown"
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            try:
                r = self.session.post(f"{self.base_url}/chat/completions", headers=self._headers(model),
                                      json=body, timeout=self.timeout)
            except requests.RequestException as e:
                last = type(e).__name__
            else:
                if r.status_code == 200:
                    j = r.json()
                    u = j.get("usage") or {}
                    ch = j["choices"][0]
                    msg = ch.get("message") or {}
                    text = msg.get("content") or ""
                    if not text.strip():  # reasoning models can leave content empty and answer inside the reasoning field
                        text = msg.get("reasoning_content") or msg.get("reasoning") or ""
                    return NimResult(text, time.time() - t0, u.get("prompt_tokens", 0), u.get("completion_tokens", 0),
                                     attempt, ch.get("finish_reason") or "")
                last = f"HTTP {r.status_code}: {_scrub(getattr(r, 'text', '') or '', key)[:200]}"
                if r.status_code not in (408, 429, 500, 502, 503, 504):
                    raise NimError(f"{model}: {last}")  # 400/401/403/404: retrying cannot help
                if r.status_code == 429:  # rate limit: honour Retry-After, else back off harder than for 5xx
                    try:
                        wait = float((getattr(r, "headers", None) or {}).get("Retry-After", ""))
                    except ValueError:
                        wait = 4.0 * attempt
                    time.sleep(min(max(wait, 2.0), 60.0))
                    continue
            time.sleep(min(2 ** attempt, 20))
        raise NimError(f"{model}: failed after {self.max_retries} attempts ({last})")


def _scrub(s: str, key: str = "") -> str:
    s = re.sub(r"nvapi-[A-Za-z0-9_\-]+", "nvapi-***", s)
    return s.replace(key, "***") if key else s


def _extra_body() -> dict:
    """Optional JSON merged into every request, e.g. NIM_EXTRA_BODY='{"chat_template_kwargs":{"enable_thinking":false}}'."""
    raw = os.getenv("NIM_EXTRA_BODY")
    if not raw:
        return {}
    try:
        d = json.loads(raw)
    except ValueError:
        raise RuntimeError("NIM_EXTRA_BODY is not valid JSON") from None
    return d if isinstance(d, dict) else {}


def parse_json(text: str) -> dict | None:
    """Last flat {...} object that parses. Tolerates code fences, <think> blocks and reasoning text before the answer."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    for m in reversed(re.findall(r"\{[^{}]*\}", text)):
        try:
            obj = json.loads(m)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


# ---------------------------------------------------------------- prompts

CLASSIFY_SYSTEM = (
    "You monitor refrigerated storage (safe band 2-8 C). Classify the LATEST row using the trend over the whole window. "
    "Typical normal values: temp 3-6 C, cooling load 45-65%, connectivity above 88%. "
    "NONE: temp inside the band, steady, nothing unusual. "
    "TEMP_EXCURSION: temp rising or above 7 C while cooling load is HIGH (above 65%): the unit is working hard against a heat load such as an open door. "
    "COOLING_FAILURE: temp rising or above 7 C while cooling load is LOW (below 40%): the compressor is not delivering. "
    "SENSOR_DROPOUT: connectivity below 50% and/or temperature and humidity repeating the exact same value for several rows; judge this first, "
    "because then the readings cannot be trusted. "
    "A single high-ish temp with normal load is NONE. "
    'Do not explain. Reply with one line of JSON only: {"label": "<class>", "confidence": <0-1>}'
)


def window_text(window: list[dict]) -> str:
    """window: oldest -> newest rows with ts, T, H, C, S. Compact table keeps tokens low."""
    lines = ["ts,temp_C,humidity_pct,cooling_load_pct,connectivity_pct"]
    for r in window:
        lines.append(f"{r['ts']},{r['T']:.2f},{r['H']:.1f},{r['C']:.1f},{r['S']:.0f}")
    return "\n".join(lines)


def classify_messages(window: list[dict]) -> list[dict]:
    return [{"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": "Readings every 30 min, oldest first:\n" + window_text(window)}]


def classify(client: NimClient, model: str, window: list[dict]) -> tuple[str, NimResult, bool]:
    """Returns (label, raw result, json_valid). Invalid output maps to 'INVALID'."""
    res = client.chat(model, classify_messages(window), max_tokens=int(os.getenv("NIM_CLASSIFY_MAX_TOKENS", "512")))
    obj = parse_json(res.text)
    label = obj.get("label") if obj else None
    if label in LABELS:
        return label, res, True
    return "INVALID", res, False


EXPLAIN_SYSTEM = (
    "You write incident notes for a cold-chain operations lead. Use ONLY the facts in the case JSON. "
    "Do not invent causes, batch IDs, times or numbers. If evidence is insufficient, say so. "
    'Reply with JSON only: {"summary": str (<=40 words), "likely_cause": str, '
    '"batches_at_risk": str, "recommended_actions": [str, str, str], "needs_human_review": bool}'
)


def explain(client: NimClient, model: str, case: dict) -> dict:
    """case: detector output + evidence (see service.Alert.to_case_json). Detector label is never changed here."""
    res = client.chat(model, [{"role": "system", "content": EXPLAIN_SYSTEM},
                              {"role": "user", "content": json.dumps(case, default=str)}], max_tokens=800)
    obj = parse_json(res.text) or {}
    actions = obj.get("recommended_actions")
    valid = (isinstance(obj.get("summary"), str) and isinstance(actions, list)
             and all(isinstance(a, str) for a in actions))
    return {"valid": valid, "model": model, "latency_s": round(res.latency_s, 2),
            "tokens": res.prompt_tokens + res.completion_tokens,
            "note": obj if valid else {"raw": res.text[:300]}}