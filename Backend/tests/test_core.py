import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coldtrace import model as M, nim
from coldtrace.evaluate import event_metrics
from coldtrace.features import FEATURES, build_features
from coldtrace.service import Detector

DATA = ROOT / "data" / "cold_chain_labeled_2022_2026.csv"
MODEL = ROOT / "artifacts" / "coldtrace_rf.joblib"
needs = pytest.mark.skipif(not (DATA.exists() and MODEL.exists()), reason="run generate_data.py and train_eval.py first")


@pytest.fixture(scope="module")
def sample():
    d = pd.read_csv(DATA, keep_default_na=False, parse_dates=["Timestamp"])
    d = d[(d.Storage_Location_ID == "JHB-DC01") & (d.Timestamp >= "2026-03-01") & (d.Timestamp < "2026-04-15")]
    return d.sort_values("Timestamp").reset_index(drop=True)


def test_event_metrics_hand_case():
    ts = pd.date_range("2026-01-01", periods=20, freq="30min")
    truth = ["NONE"] * 5 + ["COOLING_FAILURE"] * 5 + ["NONE"] * 10
    df = pd.DataFrame({"Timestamp": ts, "Storage_Location_ID": "A", "Exception_Type": truth})
    # detected 2 steps late, plus one isolated false alert of 3 steps
    pred = np.array(["NONE"] * 7 + ["COOLING_FAILURE"] * 3 + ["NONE"] * 4 + ["SENSOR_DROPOUT"] * 3 + ["NONE"] * 3, dtype=object)
    m = event_metrics(df, pred, k=2)
    t = m["per_type"]["COOLING_FAILURE"]
    assert t["events"] == 1 and t["recall_type"] == 1.0
    assert t["ttd_median_h"] == pytest.approx(1.5)  # fires at index 8, event starts at 5 -> 3 steps
    assert m["alerts"] == 2 and m["false_alerts"] == 1


@needs
def test_features_are_causal(sample):
    full = build_features(sample)
    cut = sample.iloc[:300]
    part = build_features(cut)
    pd.testing.assert_frame_equal(full.iloc[:300][FEATURES], part[FEATURES], check_exact=False, rtol=1e-9, atol=1e-9)


@needs
def test_streaming_matches_batch(sample):
    det = Detector(str(MODEL))
    batch = build_features(sample)
    rf = M.load(MODEL)["model"]
    p_batch = rf.predict_proba(batch[FEATURES])
    mism = 0
    for i, r in enumerate(sample.iloc[:350].itertuples()):
        out = det.ingest({"location_id": r.Storage_Location_ID, "ts": r.Timestamp.isoformat(), "T": r.Warehouse_Temperature_C,
                          "H": r.Warehouse_Humidity_Percent, "C": r.Cooling_Load_Percent, "S": r.Sensor_Connectivity})
        if out.status != "warming_up" and i >= 100:
            lab_b = rf.classes_[p_batch[i].argmax()]
            conf_ok = p_batch[i].max() >= det.min_conf
            lab_b = lab_b if conf_ok else "NONE"
            mism += lab_b != out.rf_label
    assert mism == 0


@needs
def test_alert_is_sealed_and_deterministic(sample):
    det = Detector(str(MODEL))
    alerts = []
    for r in sample.itertuples():
        o = det.ingest({"location_id": "JHB-DC01", "ts": r.Timestamp.isoformat(), "T": r.Warehouse_Temperature_C,
                        "H": r.Warehouse_Humidity_Percent, "C": r.Cooling_Load_Percent, "S": r.Sensor_Connectivity})
        if o.alert:
            alerts.append(o.alert)
    assert alerts, "expected at least one alert in a 6-week window"
    a = alerts[0]
    h = a.evidence_sha256
    assert len(h) == 64 and a.seal().evidence_sha256 == h
    a.evidence[0]["T"] += 1
    assert a.seal().evidence_sha256 != h  # tampering changes the hash


@needs
def test_unknown_location_rejected():
    with pytest.raises(ValueError):
        Detector(str(MODEL)).ingest({"location_id": "XXX", "ts": "2026-01-01T00:00", "T": 5, "H": 60, "C": 50, "S": 99})


def test_parse_json_tolerates_fences_and_think():
    assert nim.parse_json('<think>hmm {x}</think>```json\n{"label": "NONE", "confidence": 0.9}\n```') == {"label": "NONE", "confidence": 0.9}
    assert nim.parse_json("no json here") is None
    assert nim.parse_json('{"a": ') is None


class FakeResp:
    def __init__(self, code, body=None): self.status_code, self._b = code, body or {}
    def json(self): return self._b


class FakeSession:
    def __init__(self, codes): self.codes, self.calls = list(codes), 0
    def post(self, *a, **k):
        self.calls += 1
        c = self.codes.pop(0)
        return FakeResp(c, {"choices": [{"message": {"content": '{"label":"NONE","confidence":1}'}}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}} if c == 200 else {})


def test_nim_retries_transient_but_not_auth(monkeypatch):
    monkeypatch.setattr(nim.time, "sleep", lambda s: None)
    c = nim.NimClient(api_key="nvapi-test", session=FakeSession([429, 503, 200]))
    r = c.chat("m", [{"role": "user", "content": "x"}])
    assert r.attempts == 3 and r.prompt_tokens == 5
    c2 = nim.NimClient(api_key="nvapi-test", session=FakeSession([401, 200]))
    with pytest.raises(nim.NimError) as ei:
        c2.chat("m", [{"role": "user", "content": "x"}])
    assert c2.session.calls == 1 and "nvapi" not in str(ei.value)


def test_classify_flags_invalid_output(monkeypatch):
    class C:
        def chat(self, *a, **k): return nim.NimResult("I think it is fine", 0.1)
    lab, _, ok = nim.classify(C(), "m", [{"ts": "t", "T": 5.0, "H": 60.0, "C": 50.0, "S": 99.0}])
    assert (lab, ok) == ("INVALID", False)


# ---- per-model API keys
class HeaderSession:
    def __init__(self): self.auth = []
    def post(self, *a, headers=None, **k):
        self.auth.append(headers["Authorization"])
        return FakeResp(200, {"choices": [{"message": {"content": "{}"}}], "usage": {}})


def test_env_var_for_slug():
    assert nim.env_var_for("meta/llama-3.1-8b-instruct") == "NVIDIA_API_KEY_META_LLAMA_3_1_8B_INSTRUCT"


def test_each_model_uses_its_own_key(monkeypatch):
    for v in ("NVIDIA_API_KEY", "NIM_SECRET_NAME", "NVIDIA_API_KEYS"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv(nim.env_var_for("b/model"), "nvapi-from-env")
    s = HeaderSession()
    c = nim.NimClient(keys={"a/model": "nvapi-A", "default": "nvapi-D"}, session=s)
    for m in ("a/model", "b/model", "c/model"):
        c.chat(m, [{"role": "user", "content": "x"}])
    assert s.auth == ["Bearer nvapi-A", "Bearer nvapi-from-env", "Bearer nvapi-D"]


def test_missing_key_error_names_model_not_key(monkeypatch):
    for v in ("NVIDIA_API_KEY", "NIM_SECRET_NAME"):
        monkeypatch.delenv(v, raising=False)
    c = nim.NimClient(keys={"a/model": "nvapi-SECRET"}, session=HeaderSession())
    with pytest.raises(RuntimeError) as ei:
        c.key_for("z/model")
    assert "z/model" in str(ei.value) and "nvapi" not in str(ei.value)


def test_key_file_and_json_env(monkeypatch, tmp_path):
    f = tmp_path / "k.json"
    f.write_text('{"a/model": "nvapi-file", "b/model": "nvapi-file-b"}')
    monkeypatch.setenv("NVIDIA_KEYS_FILE", str(f))
    monkeypatch.setenv("NVIDIA_API_KEYS", '{"b/model": "nvapi-env"}')
    assert nim.load_key_map() == {"a/model": "nvapi-file", "b/model": "nvapi-env"}
    monkeypatch.setenv("NVIDIA_API_KEYS", "{bad json nvapi-LEAK")
    with pytest.raises(RuntimeError) as ei:
        nim.load_key_map()
    assert "LEAK" not in str(ei.value)


# ---- reasoning-model output and error hygiene
class _R:
    def __init__(self, code, body=None, text=""): self.status_code, self._b, self.text = code, body or {}, text
    def json(self): return self._b


class _S:
    def __init__(self, resp): self.resp = resp
    def post(self, *a, **k): return self.resp


def test_parse_json_takes_last_object_after_reasoning():
    txt = 'Let me think. Options look like {"a": 1} maybe. Final: {"label": "COOLING_FAILURE", "confidence": 0.8}'
    assert nim.parse_json(txt)["label"] == "COOLING_FAILURE"


def test_empty_content_falls_back_to_reasoning_field():
    body = {"choices": [{"message": {"content": None, "reasoning_content": 'hmm {"label": "NONE", "confidence": 1}'}, "finish_reason": "stop"}], "usage": {}}
    c = nim.NimClient(api_key="nvapi-x", session=_S(_R(200, body)))
    lab, res, ok = nim.classify(c, "m", [{"ts": "t", "T": 5.0, "H": 60.0, "C": 50.0, "S": 99.0}])
    assert (lab, ok) == ("NONE", True)


def test_http_error_shows_detail_but_scrubs_key():
    c = nim.NimClient(api_key="nvapi-SECRET123", session=_S(_R(404, text="model not found; key nvapi-SECRET123 rejected")))
    with pytest.raises(nim.NimError) as ei:
        c.chat("m", [{"role": "user", "content": "x"}])
    s = str(ei.value)
    assert "404" in s and "model not found" in s and "SECRET123" not in s


def test_extra_body_env_is_merged(monkeypatch):
    seen = {}
    class S2:
        def post(self, *a, json=None, **k):
            seen.update(json); return _R(200, {"choices": [{"message": {"content": "{}"}}], "usage": {}})
    monkeypatch.setenv("NIM_EXTRA_BODY", '{"chat_template_kwargs": {"enable_thinking": false}}')
    nim.NimClient(api_key="nvapi-x", session=S2()).chat("m", [{"role": "user", "content": "x"}])
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}