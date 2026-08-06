"""Shared config loader for Artgents agents.

Loads config/agents.yaml once at module import and provides three
schema-aware accessors matching the three distinct config shapes used
across agents:

1. get_expert_config() — single-expert agents (visual_art_historian)
2. get_dual_agent_config() — concurrent dual-agent pairs (provenance_legal,
   financial_valuation)
3. get_selectable_variant_config() — selectable-variant agents (curator)

These are NOT interchangeable — each accessor validates the specific
schema shape expected by its consumer. Using the wrong accessor for an
agent role will raise a clear error, not silently produce a wrong result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Pydantic models matching the three config shapes
# ---------------------------------------------------------------------------


class ExpertConfig(BaseModel):
    """Shape 1: Single expert agent (e.g. visual_art_historian).

    Has a single `expert` block with name/domain/voice, plus model params.
    """

    temperature: float
    max_output_tokens: int
    name: str
    domain: str
    voice: str


class SubAgentVariant(BaseModel):
    """One side of a dual-agent pair."""

    name: str
    stance: str
    voice: str


class DualAgentConfig(BaseModel):
    """Shape 2: Concurrent dual-agent pair (e.g. provenance_legal, financial_valuation).

    Has exactly 2 variants that BOTH run on every request — not selected between.
    """

    temperature: float
    max_output_tokens: int
    retrieval_description: str
    variants: dict[str, SubAgentVariant]
    synthesis_output: str

    @model_validator(mode="after")
    def _validate_exactly_two_variants(self) -> "DualAgentConfig":
        if len(self.variants) != 2:
            raise ValueError(
                f"DualAgentConfig requires exactly 2 variants, "
                f"got {len(self.variants)}: {list(self.variants.keys())}"
            )
        return self


class SelectableVariant(BaseModel):
    """One voice variant for a selectable-variant agent."""

    name: str
    voice: str


class SelectableVariantConfig(BaseModel):
    """Shape 3: Selectable-variant agent (e.g. curator).

    Has N variants with a default_variant key. ONE is selected per run.
    """

    temperature: float
    max_output_tokens: int
    variants: dict[str, SelectableVariant]
    default_variant: str

    @model_validator(mode="after")
    def _validate_default_exists(self) -> "SelectableVariantConfig":
        if self.default_variant not in self.variants:
            raise ValueError(
                f"default_variant '{self.default_variant}' not found in "
                f"variants: {list(self.variants.keys())}"
            )
        return self


# ---------------------------------------------------------------------------
# YAML loading (cached at module import)
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "agents.yaml"
_config_data: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    """Load and cache the agents.yaml config file."""
    global _config_data
    if _config_data is None:
        if not _CONFIG_PATH.exists():
            raise FileNotFoundError(
                f"Config file not found: {_CONFIG_PATH}"
            )
        with open(_CONFIG_PATH) as f:
            _config_data = yaml.safe_load(f)
        logger.debug("Loaded agent config from {}", _CONFIG_PATH)
    return _config_data


def _get_agent_section(agent_role: str) -> dict[str, Any]:
    """Get the raw config section for an agent role."""
    config = _load_config()
    if agent_role not in config:
        raise KeyError(
            f"Agent role '{agent_role}' not found in config. "
            f"Available roles: {list(config.keys())}"
        )
    return config[agent_role]


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------


def get_expert_config(agent_role: str) -> ExpertConfig:
    """Get config for a single-expert agent (shape 1).

    Expected YAML structure:
        agent_role:
          temperature: ...
          max_output_tokens: ...
          expert:
            name: ...
            domain: ...
            voice: ...

    Args:
        agent_role: The agent key in agents.yaml (e.g. "visual_art_historian").

    Returns:
        ExpertConfig with temperature, max_output_tokens, name, domain, voice.

    Raises:
        KeyError: If the agent role doesn't exist.
        ValueError: If the agent doesn't have the expected single-expert shape.
    """
    section = _get_agent_section(agent_role)

    if "expert" not in section:
        raise ValueError(
            f"Agent '{agent_role}' does not have an 'expert' block — "
            f"it may be a dual-agent or selectable-variant config. "
            f"Keys found: {list(section.keys())}"
        )

    expert = section["expert"]
    return ExpertConfig(
        temperature=section["temperature"],
        max_output_tokens=section["max_output_tokens"],
        name=expert["name"],
        domain=expert["domain"],
        voice=expert["voice"],
    )


def get_dual_agent_config(agent_role: str) -> DualAgentConfig:
    """Get config for a concurrent dual-agent pair (shape 2).

    Expected YAML structure:
        agent_role:
          temperature: ...
          max_output_tokens: ...
          retrieval:
            description: ...
          variants:
            variant_a:
              name: ...
              stance: ...
              voice: ...
            variant_b:
              name: ...
              stance: ...
              voice: ...
          synthesis_output: ...

    Both variants are ALWAYS used concurrently — this is not a selection.

    Args:
        agent_role: The agent key in agents.yaml (e.g. "provenance_legal").

    Returns:
        DualAgentConfig with temperature, max_output_tokens, retrieval_description,
        exactly 2 variants, and synthesis_output.

    Raises:
        KeyError: If the agent role doesn't exist.
        ValueError: If variants doesn't have exactly 2 keys, or the
            structure doesn't match the dual-agent shape.
    """
    section = _get_agent_section(agent_role)

    if "variants" not in section:
        raise ValueError(
            f"Agent '{agent_role}' does not have a 'variants' block — "
            f"it may be a single-expert config. Keys found: {list(section.keys())}"
        )

    if "retrieval" not in section:
        raise ValueError(
            f"Agent '{agent_role}' has variants but no 'retrieval' block — "
            f"it may be a selectable-variant config, not a dual-agent config. "
            f"Use get_selectable_variant_config() instead."
        )

    retrieval_desc = section["retrieval"]["description"]
    synthesis = section.get("synthesis_output", "")

    variants = {
        key: SubAgentVariant(**val)
        for key, val in section["variants"].items()
    }

    return DualAgentConfig(
        temperature=section["temperature"],
        max_output_tokens=section["max_output_tokens"],
        retrieval_description=retrieval_desc,
        variants=variants,
        synthesis_output=synthesis,
    )


def get_selectable_variant_config(
    agent_role: str, variant_key: str | None = None
) -> tuple[SelectableVariantConfig, SelectableVariant]:
    """Get config for a selectable-variant agent (shape 3).

    Expected YAML structure:
        agent_role:
          temperature: ...
          max_output_tokens: ...
          variants:
            variant_a:
              name: ...
              voice: ...
            variant_b:
              name: ...
              voice: ...
          default_variant: variant_a

    Args:
        agent_role: The agent key in agents.yaml (e.g. "curator").
        variant_key: Which variant to select. If None, falls back to the
            YAML's default_variant value. An explicitly invalid key
            raises — does NOT silently fall back.

    Returns:
        Tuple of (full config, selected variant).

    Raises:
        KeyError: If the agent role doesn't exist or variant_key is invalid.
        ValueError: If the structure doesn't match the selectable-variant shape.
    """
    section = _get_agent_section(agent_role)

    if "variants" not in section:
        raise ValueError(
            f"Agent '{agent_role}' does not have a 'variants' block — "
            f"it may be a single-expert config."
        )

    if "default_variant" not in section:
        raise ValueError(
            f"Agent '{agent_role}' has variants but no 'default_variant' — "
            f"it may be a dual-agent config, not a selectable-variant config. "
            f"Use get_dual_agent_config() instead."
        )

    variants = {
        key: SelectableVariant(**val)
        for key, val in section["variants"].items()
    }

    config = SelectableVariantConfig(
        temperature=section["temperature"],
        max_output_tokens=section["max_output_tokens"],
        variants=variants,
        default_variant=section["default_variant"],
    )

    # Resolve variant selection
    effective_key = variant_key if variant_key is not None else config.default_variant

    if effective_key not in config.variants:
        if variant_key is not None:
            # Explicit key was wrong — raise, do NOT fall back
            raise KeyError(
                f"Variant '{variant_key}' not found for agent '{agent_role}'. "
                f"Available variants: {list(config.variants.keys())}"
            )
        else:
            # default_variant is wrong — config error (caught by model_validator,
            # but defensive here too)
            raise KeyError(
                f"default_variant '{config.default_variant}' not found in "
                f"variants for '{agent_role}'"
            )

    return config, config.variants[effective_key]


def reset_config() -> None:
    """Reset the cached config (useful for testing)."""
    global _config_data
    _config_data = None
