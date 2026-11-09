"""Experiment configuration: loading, validation, hashing. No secrets live here."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maps.schemas import PromptVariant


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelSpec(_Cfg):
    alias: str = Field(min_length=1)
    family: str = Field(min_length=1)
    model_id: str = Field(min_length=1)


class ConditionSpec(_Cfg):
    id: str = Field(min_length=1)
    n_messages: int = Field(ge=0)
    n_roots: int = Field(ge=0)

    @model_validator(mode="after")
    def _check(self) -> ConditionSpec:
        if self.n_messages == 0:
            if self.n_roots != 0:
                raise ValueError("zero messages implies zero roots")
        elif self.n_roots not in (1, self.n_messages):
            raise ValueError("n_roots must be 1 (repeated single root) or n_messages (all independent)")
        return self


class DesignConfig(_Cfg):
    conditions: list[ConditionSpec]
    prompt_variants: list[PromptVariant]
    repetitions: int = Field(ge=1)
    rotate_templates_and_roots: bool
    scenario_dir: str
    # Primary experiment withholds evidence from the receiver (Option A). Locked by type.
    evidence_visible_to_receiver: Literal[False]

    @model_validator(mode="after")
    def _check(self) -> DesignConfig:
        ids = [c.id for c in self.conditions]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate condition ids")
        if "C0" not in ids or next(c for c in self.conditions if c.id == "C0").n_messages != 0:
            raise ValueError("conditions must include C0 as the zero-message control")
        if len(set(self.prompt_variants)) != len(self.prompt_variants):
            raise ValueError("duplicate prompt_variants")
        return self


class SamplingConfig(_Cfg):
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(gt=0)


class ApiConfig(_Cfg):
    enabled: bool = False
    base_url: str
    api_key_env: str
    timeout_s: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    backoff_s: float = Field(ge=0)


class OutputConfig(_Cfg):
    results_dir: str
    stage: Literal["pilot", "main"]


class ExperimentConfig(_Cfg):
    experiment_id: str
    config_version: str
    seed: int
    prompt_version: str
    models: list[ModelSpec] = Field(min_length=1)
    design: DesignConfig
    sampling: SamplingConfig
    api: ApiConfig
    output: OutputConfig

    @model_validator(mode="after")
    def _unique_aliases(self) -> ExperimentConfig:
        aliases = [m.alias for m in self.models]
        if len(aliases) != len(set(aliases)):
            raise ValueError("duplicate model alias")
        return self


def load_config(path: str | Path) -> ExperimentConfig:
    with open(path, encoding="utf-8") as fh:
        return ExperimentConfig.model_validate(json.load(fh))


def config_hash(cfg: ExperimentConfig) -> str:
    canonical = json.dumps(cfg.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_api_key(cfg: ExperimentConfig, environ: Mapping[str, str] | None = None) -> str | None:
    """Read the API key from the environment only. Returns None if unset/empty."""
    env = os.environ if environ is None else environ
    return env.get(cfg.api.api_key_env) or None
