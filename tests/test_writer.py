"""The LLM writer (M7): input, validator, spending safety, rendering. A fake model; no API."""

import csv
import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scout.analysis.insights import analyze
from scout.llm import LlmError
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.report.builder import build_input
from scout.report.render import render_written
from scout.report.select import select
from scout.report.validator import parse, validate
from scout.report.writer import ReportWriter, system_prompt
from scout.rules.engine import evaluate, load_rules

ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules(ROOT / "scout/rules/league_rules.yaml")
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)


@pytest.fixture
def bot_report(knowledge):
    game = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    insights = analyze(dataclasses.replace(game, my_role=Role.BOT), knowledge)
    report = select(insights, evaluate(RULES, insights))
    return report, build_input(report, insights, knowledge, 120)


def answer_for(payload, words_per_line: int = 8) -> dict:
    """A valid answer: one line per input section, citing its first item."""
    return {"sections": [
        {"key": s["key"], "lines": [{"text": " ".join(["word"] * words_per_line),
                                     "sources": [s["items"][0]["source"]]}]}
        for s in payload["sections"] if s["items"]
    ]}  # fmt: skip


class FakeModel:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, system: str, prompt: str):
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return (answer if isinstance(answer, str) else json.dumps(answer)), (5000, 400)


def make_writer(tmp_path, model, **kwargs) -> ReportWriter:
    return ReportWriter(ask=model, system="system", model="test-model",
                        usage_log=tmp_path / "usage.csv", debug_dir=tmp_path / "debug",
                        now=lambda: NOW, **kwargs)  # fmt: skip


def test_input_contract(bot_report):
    report, payload = bot_report
    assert payload["player"] == {"role": "bot", "champion": "Jhin"}
    assert payload["max_words"] == 120 and payload["patch"] == "26.19"
    assert [s["key"] for s in payload["sections"]] == [s.key for s in report.sections]
    assert "warnings" not in payload and "your_notes" not in payload  # rendered by code
    assert "Jhin" in payload["facts"]
    cp = payload["counterpick"]  # docs/COUNTERPICK.md (Output block)
    assert (cp["opponent"], cp["evidence"]["source"]) == ("Samira", "structure")
    naut = payload["facts"]["Nautilus"]
    assert naut["side"] == "enemy" and naut["key_note"]
    json.dumps(payload)  # serializable


def test_system_prompt_is_the_doc_section():
    prompt = system_prompt(ROOT / "docs/REPORT_AGENT.md")
    assert prompt.startswith("You write a short pre-game scouting report")
    assert "## What you receive" in prompt and "# PROMPT" not in prompt
    assert "Class glossary" not in prompt  # M17: no descriptions of our own


def test_validator_accepts_a_good_answer(bot_report):
    _, payload = bot_report
    assert validate(parse(answer_for(payload)), payload) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda a: a["sections"].reverse(), "keep the input's order"),
        (lambda a: a["sections"].append({"key": "made_up", "lines": []}), "unknown section keys"),
        (lambda a: a["sections"].pop(0), "missing always-on section"),
        (lambda a: a["sections"][0]["lines"][0].update(sources=[]), "cites no source"),
        (
            lambda a: a["sections"][0]["lines"][0].update(sources=["RULE-I-INVENTED"]),
            "unknown sources",
        ),
        (
            lambda a: a["sections"][0]["lines"][0].update(text="Their ADC has 4321 range."),
            "numbers not in the input: 4321",
        ),
        (
            lambda a: a["sections"][0]["lines"][0].update(text="Buy Black Cleaver early."),
            "names 'Black Cleaver'",
        ),
        (lambda a: a["sections"][0]["lines"][0].update(text="word " * 400), "words; the limit"),
    ],
)
def test_validator_problems(bot_report, change, problem):
    _, payload = bot_report
    answer = answer_for(payload)
    change(answer)
    problems = validate(parse(answer), payload, names={"Black Cleaver"})
    assert any(problem in p for p in problems), problems


def test_typography_is_plain_text():
    written = parse({"sections": [{"key": "x", "lines": [{"text": "levels 3–6 — ok",
                                                          "sources": ["A"]}]}]})  # fmt: skip
    assert written.sections[0].lines[0].text == "levels 3-6 - ok"
    joined = parse({"sections": [{"key": "x", "lines": [{"text": "targets—stand",
                                                         "sources": ["A"]}]}]})  # fmt: skip
    assert joined.sections[0].lines[0].text == "targets - stand"


def test_write_logs_usage_and_caches_the_same_draft(tmp_path, bot_report):
    _, payload = bot_report
    model = FakeModel(answer_for(payload))
    writer = make_writer(tmp_path, model)
    first = writer.write(payload)
    assert first.written is not None and first.calls == 1 and not first.cached
    again = writer.write(payload)
    assert again.cached and again.calls == 0 and len(model.prompts) == 1  # no second call
    rows = list(csv.DictReader((tmp_path / "usage.csv").open(encoding="utf-8")))
    assert [(r["model"], r["input_tokens"], r["output_tokens"], r["outcome"]) for r in rows] == [
        ("test-model", "5000", "400", "ok")
    ]  # fmt: skip
    assert rows[0]["est_cost_usd"] == "0.00700"  # 5000 x $1/M + 400 x $5/M
    assert writer.calls_today() == 1 and writer.cost_today() == pytest.approx(0.007)


def test_one_retry_with_the_problems_then_fallback(tmp_path, bot_report):
    _, payload = bot_report
    bad = answer_for(payload)
    bad["sections"][0]["lines"][0]["sources"] = ["NOPE"]
    model = FakeModel(bad, answer_for(payload))
    result = make_writer(tmp_path, model).write(payload)
    assert result.written is not None and result.calls == 2
    assert "cites unknown sources: NOPE" in model.prompts[1]
    model = FakeModel("not json", bad)
    failed = make_writer(tmp_path / "b", model).write(payload)
    assert failed.written is None and "failed its checks" in failed.note
    assert list((tmp_path / "b" / "debug").glob("*_writer_failed.json"))


def test_daily_cap(tmp_path, bot_report):
    _, payload = bot_report
    model = FakeModel(answer_for(payload), answer_for(payload))
    writer = make_writer(tmp_path, model, max_calls_per_day=1)
    assert writer.write(payload).written is not None
    other = dict(payload, max_words=121)  # a different draft
    capped = writer.write(other)
    assert capped.written is None and "daily writer limit reached (1 calls)" in capped.note
    assert len(model.prompts) == 1


def test_api_errors_fall_back_quietly(tmp_path, bot_report):
    _, payload = bot_report
    result = make_writer(tmp_path, FakeModel(LlmError("out of credit"))).write(payload)
    assert result.written is None and "out of credit" in result.note
    assert make_writer(tmp_path, FakeModel()).calls_today() == 0  # errors don't count


def test_render_written(bot_report):
    report, payload = bot_report
    answer = answer_for(payload)
    answer["sections"][0]["lines"][0]["text"] = "Short written line."
    text = render_written(report, parse(answer), debug=True)
    assert text.startswith("Sidekick: bot Jhin")
    assert "YOUR LANE\n- Short written line.  [insight:lane_timeline]" in text
    assert "WARNINGS" in text  # from code, not the model


def test_watcher_writes_only_at_the_loading_screen(knowledge, tmp_path):
    """Two phases: the free rules report when picks lock; the LLM writes the final report at
    the loading screen, once (2026-10-02)."""
    from test_watcher import JUNGLER, loading_roster, make_watcher, replay

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    calls = []

    def answer(system, prompt):
        payload = json.loads(prompt)
        calls.append(payload)
        return json.dumps(answer_for(payload)), (5000, 400)

    watcher.writer = make_writer(tmp_path / "w", answer)
    watcher.write_in_background = False
    shown = []
    watcher.on_report = lambda title, text: shown.append(title)
    replay(watcher, clock)
    assert shown == [] and calls == []  # champ select: no report at all (2026-10-03)
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))
    assert len(calls) == 1
    assert shown == ["Report with roles confirmed (jungle, Jax)"]  # only the written one
    assert any(m.startswith("Report with roles confirmed, written (1 call(s))") for m in messages)
    saved = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "## Rules version" in saved


class SlowStats:
    """Stats still loading when the final report goes out, then in."""

    opgg = None  # no players' records in this test

    def __init__(self) -> None:
        self.loading = True

    def for_game(self, game, budget_s=0.0):
        from scout.analysis.stats import NO_STATS

        return NO_STATS

    def busy(self) -> bool:
        return self.loading

    def prefetch(self, game) -> None:
        pass


def test_stats_arriving_after_the_final_report_keep_it_final_and_written(knowledge, tmp_path):
    """The audit's catch (2026-10-03): a late-stats re-render after the final report used to
    fall back to the draft read and drop the written version."""
    from test_watcher import JUNGLER, loading_roster, make_watcher, replay

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    calls = []

    def answer(system, prompt):
        calls.append(json.loads(prompt))
        return json.dumps(answer_for(calls[-1])), (5000, 400)

    watcher.writer = make_writer(tmp_path / "w", answer)
    watcher.write_in_background = False
    views = []
    watcher.on_view = views.append
    replay(watcher, clock)
    watcher.stats = SlowStats()
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))
    assert len(calls) == 1 and watcher.live.stats_pending
    watcher.stats.loading = False
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))  # still the loading screen
    assert any(m.startswith("Final report (stats arrived)") for m in messages)
    assert len(calls) == 1  # the same input here: the written text is reused, no second call
    reports = [v for v in views if v["screen"] == "report"]
    assert reports and all(v["written"] for v in reports)  # never a rules or draft screen
    assert views[-1]["screen"] == "report" and views[-1]["written"]


def test_background_work_waits_for_any_game(knowledge, tmp_path):
    """Swiftplay has no champ select and the app can open mid-game: the watcher isn't following
    that game, but background work still waits."""
    from test_watcher import make_watcher

    watcher, _, _ = make_watcher(knowledge, tmp_path)
    assert watcher.idle()
    watcher.process("InProgress", None, {})
    assert watcher.state == "idle" and not watcher.idle()
    watcher.process("EndOfGame", None, {})
    assert watcher.idle()  # the game is over
    watcher.process("ChampSelect", None)  # the session isn't ready yet
    assert not watcher.idle()
    watcher.process("Lobby", None)
    assert watcher.idle()


def test_one_report_written_with_the_duos_and_writing_shown_until_then(knowledge, tmp_path):
    """2026-10-03: straight from champ select to the LLM report, with the summoner
    spells, roles and duos in it; nothing else is shown as the report."""
    from test_watcher import JUNGLER, loading_roster, make_watcher, replay

    watcher, _, clock = make_watcher(knowledge, tmp_path)
    calls = []

    def answer(system, prompt):
        calls.append(json.loads(prompt))
        return json.dumps(answer_for(calls[-1])), (5000, 400)

    watcher.writer = make_writer(tmp_path / "w", answer)
    watcher.write_in_background = False
    watcher.riot = object()  # the duo check runs; its lookups are replaced here
    duo = "Their Gragas and Karma have played several recent games together on the same team."
    watcher._check_enemies = lambda *args: [duo]
    views = []
    watcher.on_view = views.append
    replay(watcher, clock)
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))
    loading = [s for s in calls[0]["sections"] if s["key"] == "loading_screen"]
    assert [i["text"] for i in loading[0]["items"]] == [duo]  # the writer got the duo line
    states = [v["state"] for v in views if v["screen"] == "status"]
    assert states[-2:] == ["picks_locked", "writing"]
    reports = [v for v in views if v["screen"] == "report"]
    assert reports and all(v["written"] for v in reports)
    assert any(s["key"] == "loading_screen" for s in reports[-1]["sections"])


def test_if_the_ai_fails_the_rules_version_is_shown_labelled(knowledge, tmp_path):
    from test_watcher import JUNGLER, loading_roster, make_watcher, replay

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    watcher.writer = make_writer(tmp_path / "w", lambda system, prompt: ("not json", (10, 10)))
    watcher.write_in_background = False
    views = []
    watcher.on_view = views.append
    replay(watcher, clock)
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))
    last = views[-1]
    assert last["screen"] == "report" and not last["written"]
    assert any(w.startswith("The AI writer didn't write this one") for w in last["warnings"])
    assert any("showing the rules version" in m for m in messages)
