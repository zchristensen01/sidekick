"""Render a report as plain text for the terminal, the window and reports/<timestamp>_<champ>.md.

Two views of the same report: the deterministic one (selected items as bullets, also the
fallback) and the written one (the LLM's lines, M7). Section titles, your notes and warnings
always come from code. `debug` shows the source of every line.
"""

import textwrap

from scout.model.roles import Role
from scout.report.select import Report
from scout.report.validator import Written

WIDTH = 100


def render_text(report: Report, debug: bool = False) -> str:
    lines = _header(report)
    for section in report.sections:
        lines += ["", section.title.upper()]
        for item in section.items:
            tag = f"  [{item.source}]" if debug else ""
            lines += _bullet(item.text + tag)
    return "\n".join(lines + _footer(report)) + "\n"


def render_written(report: Report, written: Written, debug: bool = False) -> str:
    titles = {s.key: s.title for s in report.sections}
    lines = _header(report)
    for section in written.sections:
        if not section.lines:
            continue
        lines += ["", titles.get(section.key, section.key).upper()]
        for line in section.lines:
            tag = f"  [{', '.join(line.sources)}]" if debug else ""
            lines += _bullet(line.text + tag)
    return "\n".join(lines + _footer(report)) + "\n"


def _header(report: Report) -> list[str]:
    def team(picks: dict[Role, str]) -> str:
        return " / ".join(picks.get(r, "?") for r in Role)

    return [
        f"Sidekick: {report.role.value} {report.champion} "
        f"(patch {report.patch}, {report.queue.replace('_', ' ')}"
        + (f", {report.side} side)" if report.side else ")"),
        f"  You:  {team(report.ally)}",
        f"  Them: {team(report.enemy)}",
    ]


def _footer(report: Report) -> list[str]:
    lines: list[str] = []
    if report.your_notes:
        lines += ["", "YOUR NOTES"]
        for note in report.your_notes:
            lines += _bullet(note)
    if report.warnings:
        lines += ["", "WARNINGS"]
        for warning in report.warnings:
            lines += _bullet(warning)
    return lines


def _bullet(text: str) -> list[str]:
    return textwrap.wrap(text, WIDTH, initial_indent="- ", subsequent_indent="  ") or ["-"]
