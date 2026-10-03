"""`scout draft-traits`: have an LLM draft a champion_traits.csv row for the owner to review.

The prompt holds only the rubric (read from docs/TRAITS.md at runtime) and the champion's data
(static facts, Riot's ratings, Riot's ability text). No League facts live in this code
(CLAUDE.md hard rule 3). The answer is structured JSON, checked by the same validator as the
file, retried once with the problems listed, and appended with reviewed=n, source=llm.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scout import llm
from scout.data.schemas import CHAMPION_TRAITS, TRAIT_SCALES, TRAIT_TAGS
from scout.data.store import Row, TraitContext, validate_traits

MAX_OUTPUT_TOKENS = 2000
RUBRIC_SECTIONS = ("Columns", "Scales (rubric)", "Tag vocabulary")
TEXT_FIELDS = ("key_note", "ult_note", "spike_note")

# The JSON the model must return. Scores are enums so they can't leave 0-3.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        **{scale: {"type": "integer", "enum": [0, 1, 2, 3]} for scale in TRAIT_SCALES},
        "spikes": {"type": "array", "items": {"type": "integer"}},
        "tags": {"type": "array", "items": {"type": "string", "enum": sorted(TRAIT_TAGS)}},
        "style": {"type": "string", "enum": ["", "ganker", "farmer"]},
        **{name: {"type": "string"} for name in TEXT_FIELDS},
        "notes": {"type": "string"},
    },
    "required": [*TRAIT_SCALES, "spikes", "tags", "style", *TEXT_FIELDS, "notes"],
    "additionalProperties": False,
}


class DraftError(Exception):
    """Drafting failed; the message says why and what to do."""


@dataclass
class DraftResult:
    row: Row
    attempts: int
    input_tokens: int
    output_tokens: int


Ask = llm.Ask


def champion_brief(tables: dict[str, list[Row]], champ_id: str) -> str:
    """The champion's facts and Riot's ability text, as plain text for a prompt or a screen."""
    champion = next((r for r in tables.get("champions.csv", []) if r["champ_id"] == champ_id), None)
    if champion is None:
        raise DraftError(f"{champ_id} isn't in champions.csv; run `scout refresh` first.")
    meta = next((r for r in tables.get("champion_meta.csv", []) if r["champ_id"] == champ_id), {})
    lines = [
        f"{champion['name']} (champ_id: {champ_id})",
        f"positions: {meta.get('positions') or '?'} | classes: {meta.get('classes') or '?'} | "
        f"range: {meta.get('range_type') or '?'} | damage: {meta.get('damage_type') or '?'}",
        "Riot ratings (1-3, whole kit including the ultimate): "
        + ", ".join(
            f"{name} {meta.get(column) or '?'}"
            for name, column in (
                ("damage", "rating_damage"),
                ("durability", "rating_durability"),
                ("cc", "rating_cc"),
                ("mobility", "rating_mobility"),
                ("utility", "rating_utility"),
                ("difficulty", "difficulty"),
            )
        ),  # fmt: skip
    ]
    for ability in tables.get("abilities.csv", []):
        if ability["champ_id"] == champ_id:
            cooldowns = f" (cooldowns {ability['cooldowns']})" if ability["cooldowns"] else ""
            lines.append(
                f"- {ability['slot']} {ability['name']}{cooldowns}: {ability['description']}"
            )
    return "\n".join(lines)


def rubric(traits_doc: Path) -> str:
    """The rubric sections of docs/TRAITS.md, verbatim."""
    text = traits_doc.read_text(encoding="utf-8")
    parts = []
    for title in RUBRIC_SECTIONS:
        match = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if not match:
            raise DraftError(f"docs/TRAITS.md has no '## {title}' section")
        parts.append(f"## {title}\n{match.group(1).strip()}")
    return "\n\n".join(parts)


def system_prompt(traits_doc: Path, examples: list[Row]) -> str:
    shown = "\n".join(
        json.dumps({k: row[k] for k in CHAMPION_TRAITS if k not in ("reviewed", "reviewed_patch",
                                                                    "source", "notes", "role")})
        for row in examples
    )  # fmt: skip
    return (
        "You draft one row of a League of Legends champion traits table for a pre-game "
        "scouting app. The owner reviews every draft, so be accurate and conservative.\n\n"
        f"{rubric(traits_doc)}\n\n"
        "Rules for your answer:\n"
        "- Base every claim on the ability text you are given; never contradict it. If you "
        "don't know the champion well, rely on the text alone and say so in notes.\n"
        "- Text fields: plain language, abilities by their Riot name, no item names, and no "
        "numbers except level numbers and numbers that appear in the ability text.\n"
        "- key_note at most 240 characters, ult_note at most 320, spike_note at most 200.\n"
        "- spikes: levels with big power jumps, ascending. style: only for junglers.\n"
        "- When unsure between two scores, pick the lower and say why in notes.\n\n"
        + (f"Rows the owner has checked, for calibration:\n{shown}\n" if shown else "")
    )


def to_row(champ_id: str, answer: dict[str, Any]) -> Row:
    """The model's JSON as a champion_traits.csv row (reviewed=n, source=llm)."""
    row = dict.fromkeys(CHAMPION_TRAITS, "")
    row["champ_id"] = champ_id
    for scale in TRAIT_SCALES:
        row[scale] = str(answer.get(scale, ""))
    row["spikes"] = "|".join(str(s) for s in sorted(set(answer.get("spikes") or [])))
    row["tags"] = "|".join(answer.get("tags") or [])
    row["style"] = str(answer.get("style") or "")
    for name in TEXT_FIELDS:
        row[name] = " ".join(str(answer.get(name) or "").split())
    row["reviewed"], row["source"] = "n", "llm"
    row["notes"] = " ".join(str(answer.get("notes") or "").split())
    return row


def draft(
    champ_id: str,
    tables: dict[str, list[Row]],
    context: TraitContext,
    traits_doc: Path,
    examples: list[Row],
    ask: Ask,
    version: str,
) -> DraftResult:
    """Draft and validate one row. One retry with the validator's problems, then give up."""
    system = system_prompt(traits_doc, examples)
    prompt = (
        f"Draft the traits row for this champion (patch data {version}).\n\n"
        f"{champion_brief(tables, champ_id)}"
    )
    tokens_in = tokens_out = 0
    problems: list[str] = []
    for attempt in (1, 2):
        try:
            text, (used_in, used_out) = ask(system, prompt)
        except llm.LlmError as exc:
            raise DraftError(str(exc)) from None
        tokens_in, tokens_out = tokens_in + used_in, tokens_out + used_out
        try:
            row = to_row(champ_id, json.loads(text))
        except (json.JSONDecodeError, AttributeError) as exc:
            problems = [f"the answer wasn't the JSON object asked for ({exc})"]
        else:
            note = f"drafted from {version} ability text"
            row["notes"] = f"{note}; {row['notes']}" if row["notes"] else note
            problems = validate_traits([row], context)
            if not problems:
                return DraftResult(row, attempt, tokens_in, tokens_out)
        prompt += "\n\nYour previous answer had these problems; fix them:\n- " + "\n- ".join(
            problems
        )
    raise DraftError(f"{champ_id}: the draft failed validation twice: {'; '.join(problems)}")


def anthropic_ask(model: str, api_key: str) -> Ask:
    """An Ask that calls the Anthropic API with this module's JSON schema."""
    return llm.anthropic_ask(model, api_key, SCHEMA, MAX_OUTPUT_TOKENS)


def missing_champions(tables: dict[str, list[Row]], traits_rows: list[Row]) -> list[str]:
    """Champions in the static data with no traits row at all, alphabetically."""
    have = {row["champ_id"] for row in traits_rows}
    return sorted(
        r["champ_id"] for r in tables.get("champions.csv", []) if r["champ_id"] not in have
    )


def example_rows(traits_rows: list[Row], limit: int = 6) -> list[Row]:
    """Calibration examples for the prompt: The owner's reviewed rows first, then prototype rows."""
    reviewed = [r for r in traits_rows if r["reviewed"] == "y"]
    prototype = [r for r in traits_rows if r["source"] == "prototype" and r["ult_note"]]
    return (reviewed + prototype)[:limit]

