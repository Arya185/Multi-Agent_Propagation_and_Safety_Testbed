"""A tiny mock-executor helper for the live-executor tests (the mock executor must stay unchanged)."""

from __future__ import annotations

from types import SimpleNamespace

from maps.runs.executor import execute_mock_run

from le_support import CLOCK, REPO_ROOT, provenance_options


def MOCK_RUN(tmp_path, exception: BaseException):
    """Run the MOCK executor with a runner that raises ``exception``."""

    def runner(cfg, scenarios, client, out_dir, secrets=None, repo_root=REPO_ROOT):
        raise exception

    cfg = SimpleNamespace(api=SimpleNamespace(enabled=False))
    return execute_mock_run(run_fn=runner, cfg=cfg, scenarios=[], client=SimpleNamespace(name="mock"), run_dir=tmp_path / "run",
                            run_id="mock-int", repo_root=REPO_ROOT, provenance_options=provenance_options(), clock=CLOCK)
