"""Have the LLM write the report from the input JSON, safely and cheaply.

System prompt = the PROMPT part of docs/REPORT_AGENT.md, read at runtime. One retry with the
validator's problems, then the deterministic report is used instead. Spending safety (the owner's
request): the same draft never costs a second call (cached), there's a daily call cap, output
tokens are capped, and every call is logged with tokens and estimated cost.
"""

import csv
import hashlib
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scout.llm import Ask, LlmError
from scout.report.validator import Written, parse, validate

USAGE_COLUMNS = ("time", "model", "input_tokens", "output_tokens", "est_cost_usd", "outcome",
                 "seconds")  # fmt: skip
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "lines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "sources": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["text", "sources"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["key", "lines"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}


def system_prompt(report_agent_doc: Path) -> str:
    """Everything under '# PROMPT' in docs/REPORT_AGENT.md."""
    text = report_agent_doc.read_text(encoding="utf-8")
    marker = "\n# PROMPT\n"
    if marker not in text:
        raise ValueError(f"{report_agent_doc} has no '# PROMPT' section")
    return text.split(marker, 1)[1].strip()


@dataclass
class WriteResult:
    written: Written | None
    note: str  # why there's no written version, or "" when there is
    calls: int = 0
    cached: bool = False


@dataclass
class ReportWriter:
    ask: Ask
    system: str
    model: str
    usage_log: Path
    debug_dir: Path
    max_calls_per_day: int = 40
    price_in: float = 1.0  # USD per million input tokens
    price_out: float = 5.0
    names: Iterable[str] = ()  # item and ability names, for the validator
    now: Callable[[], datetime] = lambda: datetime.now().astimezone()
    _cache: dict[str, Written] = field(default_factory=dict)

    def write(self, payload: dict[str, Any]) -> WriteResult:
        key = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if key in self._cache:
            return WriteResult(self._cache[key], "", cached=True)
        used = self.calls_today()
        if used >= self.max_calls_per_day:
            return WriteResult(None, f"daily writer limit reached ({used} calls); showing the "
                               "rules report (llm.max_calls_per_day in config.yaml)")  # fmt: skip
        prompt = json.dumps(payload, ensure_ascii=False)
        problems: list[str] = []
        raw_outputs: list[str] = []
        calls = 0
        for attempt in (1, 2):
            if self.calls_today() >= self.max_calls_per_day:
                break
            started = time.monotonic()
            try:
                text, (tokens_in, tokens_out) = self.ask(self.system, prompt)
            except LlmError as exc:
                self._log(0, 0, f"error: {exc}", time.monotonic() - started)
                return WriteResult(None, f"writer unavailable ({exc}); showing the rules report",
                                   calls)  # fmt: skip
            calls += 1
            raw_outputs.append(text)
            try:
                written = parse(json.loads(text))
            except ValueError as exc:  # JSONDecodeError is a ValueError
                problems = [f"the answer wasn't the JSON asked for ({exc})"]
            else:
                problems = validate(written, payload, self.names)
            outcome = "ok" if not problems else f"invalid (attempt {attempt}): {problems[0][:120]}"
            self._log(tokens_in, tokens_out, outcome, time.monotonic() - started)
            if not problems:
                self._cache[key] = written
                return WriteResult(written, "", calls)
            prompt += ("\n\nYour previous answer had these problems; fix them and answer again:"
                       "\n- " + "\n- ".join(problems))  # fmt: skip
        self._save_debug(payload, raw_outputs, problems)
        return WriteResult(None, "the written version failed its checks; showing the rules report",
                           calls)  # fmt: skip

    def calls_today(self) -> int:
        today = self.now().date().isoformat()
        return sum(1 for row in self._rows() if row.get("time", "").startswith(today)
                   and not row.get("outcome", "").startswith("error"))  # fmt: skip

    def cost_today(self) -> float:
        today = self.now().date().isoformat()
        return sum(float(row.get("est_cost_usd") or 0) for row in self._rows()
                   if row.get("time", "").startswith(today))  # fmt: skip

    def _rows(self) -> list[dict[str, str]]:
        if not self.usage_log.exists():
            return []
        with self.usage_log.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _log(self, tokens_in: int, tokens_out: int, outcome: str, seconds: float) -> None:
        cost = tokens_in / 1e6 * self.price_in + tokens_out / 1e6 * self.price_out
        new = not self.usage_log.exists()
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)
        with self.usage_log.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            if new:
                writer.writerow(USAGE_COLUMNS)
            writer.writerow([self.now().isoformat(timespec="seconds"), self.model, tokens_in,
                             tokens_out, f"{cost:.5f}", outcome, f"{seconds:.1f}"])  # fmt: skip

    def _save_debug(self, payload: dict[str, Any], outputs: list[str], problems: list[str]) -> None:
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.now().strftime("%Y-%m-%d_%H%M%S")
        body = {"problems": problems, "outputs": outputs, "input": payload}
        (self.debug_dir / f"{stamp}_writer_failed.json").write_text(
            json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def usage_today(usage_log: Path, today: str) -> tuple[int, float]:
    """(calls, estimated USD) logged today, for `scout doctor`."""
    if not usage_log.exists():
        return 0, 0.0
    with usage_log.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("time", "").startswith(today)]
    calls = sum(1 for r in rows if not r.get("outcome", "").startswith("error"))
    return calls, sum(float(r.get("est_cost_usd") or 0) for r in rows)
