"""Single-call OpenRouter smoke test. DIAGNOSTIC ONLY — NOT AN EXPERIMENT RUN. SPENDS A TINY AMOUNT OF CREDITS.

This script is a standalone connectivity check. It is NOT part of the research execution path:
  * it uses no run directory, claim, policy, budget wrapper, provenance, event log or integrity report, and it writes
    no files, so nothing it does can become, or be mistaken for, an experiment run or an analysis input;
  * it makes AT MOST ONE provider request per invocation: retries are fixed at zero (``DIAGNOSTIC_MAX_RETRIES``)
    whatever the configuration says, and it calls the client exactly once. The client does not follow redirects.

Refuses to run without --confirm-spend, api.enabled=true in the config, and the API key in the environment (or .env).
Do not run without explicit approval. It is listed in the provider-route allow-list (tests/provider_routes) as a
``diagnostic_only`` route. The configured ``api.base_url`` is still not validated (a Stage 4E item).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from maps.config import get_api_key, load_config  # noqa: E402
from maps.llm_client import OpenRouterClient  # noqa: E402
from maps.logging_utils import redact  # noqa: E402
from maps.schemas import ChatMessage, ChatRequest  # noqa: E402

DIAGNOSTIC_BANNER = "DIAGNOSTIC — NOT AN EXPERIMENT RUN"
DIAGNOSTIC_MAX_RETRIES = 0   # fixed: this script never retries, whatever api.max_retries says in the configuration


def main(argv: list[str] | None = None, *, session=None, environ=None) -> int:
    """Run the diagnostic. ``session`` (a fake transport) and ``environ`` (a mapping) exist only so tests can run it offline."""
    print(DIAGNOSTIC_BANNER)
    print("At most one provider request; retries are disabled for this script; no files are written.")
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT / "configs/receiver_experiment.json"))
    p.add_argument("--model-alias", default=None, help="defaults to the first configured model")
    p.add_argument("--confirm-spend", action="store_true")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    if not args.confirm_spend or not cfg.api.enabled:
        print("refused: needs --confirm-spend and api.enabled=true in the config", file=sys.stderr)
        return 2
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    key = get_api_key(cfg, environ)
    if not key:
        print(f"refused: {cfg.api.api_key_env} is not set", file=sys.stderr)
        return 2
    model = next((m for m in cfg.models if m.alias == args.model_alias), cfg.models[0])
    client = OpenRouterClient(
        key, base_url=cfg.api.base_url, timeout_s=cfg.api.timeout_s,
        max_retries=DIAGNOSTIC_MAX_RETRIES, backoff_s=cfg.api.backoff_s, enabled=True,
        **({} if session is None else {"session": session}),
    )
    result = client.complete(
        ChatRequest(
            model=model.model_id,
            messages=[ChatMessage(role="user", content="Reply with the single word: ok")],
            temperature=0.0,
            max_tokens=16,
            seed=0,
        )
    )
    print(redact(result.model_dump_json(indent=2), [key]))
    return 1 if result.error else 0


if __name__ == "__main__":
    raise SystemExit(main())
