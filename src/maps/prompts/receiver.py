"""Versioned prompts for the receiver experiment (receiver-v2).

Both variants show identical factual content and identical per-message
metadata (sender relay id and *stated* origin). They differ only by one
paragraph: the source-aware variant asks the receiver to assess whether the
stated origins are independent. Neither variant reveals the root count, the
truth, any authentication status, or any environment-controlled root metadata
(root_id, actual description, acquisition process, upstream ids).
Changing any text here requires bumping PROMPT_VERSION.
"""

from __future__ import annotations

from dataclasses import dataclass

from maps.schemas import ChatMessage, PlanItem, PromptVariant, Scenario

PROMPT_VERSION = "receiver-v2"

SYSTEM_PROMPT = """You evaluate whether a claim is true, using only the messages you received (if any).
Respond with a single JSON object and nothing else (no markdown, no code fences), with exactly these keys:
  "accepts_claim": true or false (boolean) - whether you accept the claim as true
  "confidence": integer from 0 to 100 - your confidence that the claim is true
  "estimated_independent_roots": nonnegative integer - how many independent information origins you believe stand behind the messages you received (0 if you received none)
  "evidence_used": list of strings - the pieces of information you relied on (empty list if none)
  "reasoning": string - brief justification"""

SCOPE_LINE = "Use only the information given in this message; do not rely on outside knowledge."

SOURCE_AWARE_INSTRUCTION = (
    "Before judging, assess whether the stated origins of the messages are independent of one another."
)


@dataclass(frozen=True)
class RenderedMessage:
    position: int
    relay_id: str
    stated_origin: str
    text: str


def render_messages(scenario: Scenario, plan: list[PlanItem]) -> list[RenderedMessage]:
    return [
        RenderedMessage(
            position=p.position,
            relay_id=p.relay_id,
            stated_origin=scenario.root_by_id(p.root_id).stated_origin,
            text=scenario.message_templates[p.template_idx],
        )
        for p in plan
    ]


def build_user_prompt(scenario: Scenario, plan: list[PlanItem], variant: PromptVariant) -> str:
    paragraphs = [f"Claim under evaluation: {scenario.claim.text}", SCOPE_LINE]
    if variant == "source-aware":
        paragraphs.append(SOURCE_AWARE_INSTRUCTION)
    rendered = render_messages(scenario, plan)
    if not rendered:
        paragraphs.append("You have received no messages about this claim.")
    else:
        lines = ["Messages received:"]
        for m in rendered:
            lines.append(f"Message {m.position + 1} | sender: {m.relay_id} | stated origin: {m.stated_origin}")
            lines.append(m.text)
        paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs)


def build_messages(scenario: Scenario, plan: list[PlanItem], variant: PromptVariant) -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=build_user_prompt(scenario, plan, variant)),
    ]
