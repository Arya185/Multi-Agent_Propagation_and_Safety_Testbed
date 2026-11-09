"""Builders for the Stage 4E live-CLI flow tests (v2.3.74). OFFLINE ONLY.

Inputs are the SYNTHETIC configuration and scenarios (96 episodes). The policy is generated in a temporary directory with
synthetic values; the client is a scripted fake supplied through an injected factory. Nothing reads a credential or ``.env``,
builds the real provider client, or reaches a network.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in ("policy_source", "live_executor"):
    sys.path.insert(0, str(REPO_ROOT / "tests" / extra))

import ps_support  # noqa: E402
from le_support import Factory, ScriptedClient  # noqa: E402

from maps.config import load_config  # noqa: E402
from maps.runs.endpoint_policy import APPROVED_HOSTS, APPROVED_PATH, validate_base_url  # noqa: E402
from maps.runs.policy_source import load_policy, policy_digest  # noqa: E402

SECRET = "SENTINEL-SECRET-VALUE-4242"


def approved_base_url() -> str:
    return f"https://{APPROVED_HOSTS[0]}{APPROVED_PATH}"


def write_config(tmp_path: Path, *, enabled: bool = True) -> Path:
    config = json.loads(ps_support.SYN_CONFIG.read_text(encoding="utf-8"))
    config["api"].update({"enabled": enabled, "base_url": approved_base_url()})
    config["output"]["results_dir"] = str(tmp_path / "results")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def prepare(tmp_path: Path, *, enabled: bool = True, limits: dict | None = None):
    """(cfg, scenarios, specs, loaded policy, endpoint) for the synthetic inputs, with optional profile limit overrides."""
    config_path = write_config(tmp_path, enabled=enabled)
    cfg = load_config(config_path)
    _cfg, scenarios, specs, digests = ps_support.load_inputs(config_path)
    doc = ps_support.make_doc(cfg, specs, digests)
    if limits:
        doc["profiles"][ps_support.PROFILE].update(limits)
    path = ps_support.write_policy(tmp_path, doc)
    loaded = load_policy(path, cfg=cfg, specs=specs, content_digests=digests, profile=ps_support.PROFILE, expected_digest=policy_digest(doc))
    return cfg, scenarios, specs, loaded, validate_base_url(cfg.api.base_url)


def client_factory(**kwargs) -> Factory:
    kwargs.setdefault("max_retries", 2)                 # must equal the synthetic configuration and the policy
    return Factory(ScriptedClient(**kwargs))
