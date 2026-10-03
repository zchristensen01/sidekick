"""Check the writer's output before it's shown (docs/REPORT_AGENT.md, Validator).

- Section keys are a subset of the input's, in the same order; every `always` section is there.
- Every line cites at least one source, and every source exists in the input.
- Every number in a line appears somewhere in the input.
- Any item or ability name in the output appears in the input.
- Total words are at most max_words x 2.5 (the target itself is a soft limit, in the prompt).
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# Length is a soft target: a report somewhat over it is still far shorter than the rules
# version, and retries don't shorten it reliably, so only an absurd length is rejected.
WORD_SLACK = 2.5
_TYPOGRAPHY = str.maketrans({
    "–": "-", "—": " - ", "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...",
})  # fmt: skip


@dataclass(frozen=True)
class Line:
    text: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class WrittenSection:
    key: str
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class Written:
    sections: tuple[WrittenSection, ...] = field(default_factory=tuple)


def parse(raw: Any) -> Written:
    """The writer's JSON as a Written report. Raises ValueError if the shape is wrong."""
    if not isinstance(raw, dict) or not isinstance(raw.get("sections"), list):
        raise ValueError("expected an object with a `sections` list")
    sections = []
    for s in raw["sections"]:
        if not isinstance(s, dict) or not isinstance(s.get("lines"), list):
            raise ValueError("each section needs `key` and `lines`")
        lines = tuple(
            Line(" ".join(str(line.get("text", "")).translate(_TYPOGRAPHY).split()),
                 tuple(str(x) for x in line.get("sources") or []))
            for line in s["lines"] if isinstance(line, dict)
        )  # fmt: skip
        sections.append(WrittenSection(str(s.get("key", "")), lines))
    return Written(tuple(sections))


REASONING = "reasoning"  # the writer's own read where Sidekick has no data (M19)
REASONING_PREFIX = "No data; AI read:"


def validate(
    written: Written,
    payload: dict[str, Any],
    names: Iterable[str] = (),
) -> list[str]:
    """Problems with the output; empty means it can be shown. `names`: every item and ability
    name in the static data (anything named in the output must also be in the input)."""
    problems: list[str] = []
    input_sections = payload["sections"]
    order = [s["key"] for s in input_sections]
    keys = [s.key for s in written.sections]
    unknown = [k for k in keys if k not in order]
    if unknown:
        problems.append(f"unknown section keys: {', '.join(unknown)}")
    known = [k for k in keys if k in order]
    if known != sorted(known, key=order.index) or len(set(known)) != len(known):
        problems.append("sections must keep the input's order, each once")
    for s in input_sections:
        if s["always"] and s["key"] not in keys:
            problems.append(f"missing always-on section {s['key']}")

    sources = {item["source"] for s in input_sections for item in s["items"]}
    sources |= {f"fact:{name}" for name in payload.get("facts", {})}
    gaps = any(f.get("off_role") or f.get("no_data") for f in payload.get("facts", {}).values())
    if gaps:  # M19: where there's no data, the writer may add its own read, labelled
        sources.add(REASONING)
    input_text = json.dumps(payload, ensure_ascii=False)
    allowed_numbers = set(_NUMBER.findall(input_text))
    words = 0
    for section in written.sections:
        for line in section.lines:
            where = f'{section.key}: "{line.text[:40]}..."'
            if not line.text:
                problems.append(f"{section.key}: empty line")
                continue
            words += len(line.text.split())
            if not line.sources:
                problems.append(f"{where} cites no source")
            bad = [x for x in line.sources if x not in sources]
            if bad:
                problems.append(f"{where} cites unknown sources: {', '.join(bad)}")
            if REASONING in line.sources and not line.text.startswith(REASONING_PREFIX):
                problems.append(f"{where} is the AI's own read but doesn't start with "
                                f"{REASONING_PREFIX!r}")  # fmt: skip
            stray = sorted(set(_NUMBER.findall(line.text)) - allowed_numbers)
            if stray:
                problems.append(f"{where} has numbers not in the input: {', '.join(stray)}")
            for name in names:
                if (re.search(rf"(?<!\w){re.escape(name)}(?!\w)", line.text)
                        and name not in input_text):  # fmt: skip
                    problems.append(f"{where} names {name!r}, which isn't in the input")
    limit = int(payload["max_words"] * WORD_SLACK)
    if words > limit:
        problems.append(f"{words} words; the limit is {payload['max_words']}")
    return problems
