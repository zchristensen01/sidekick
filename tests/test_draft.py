"""`scout draft-traits`: prompt, structured answer, validation and retry, appending. No API."""

import json

import pytest
from typer.testing import CliRunner

from scout.cli import app
from scout.data.draft import (
    SCHEMA,
    DraftError,
    champion_brief,
    draft,
    example_rows,
    missing_champions,
    rubric,
    system_prompt,
    to_row,
)
from scout.data.schemas import CHAMPION_TRAITS
from scout.data.store import TraitContext, append_traits, read_csv, write_csv

GOOD = {
    "early": 3, "engage": 3, "cc": 3, "escape": 0, "scaling": 1, "roam": 1, "waveclear": 1,
    "frontline": 3, "spikes": [6, 2], "tags": ["airborne", "ult_engage"], "style": "",
    "key_note": "Dredge Line is his main engage; if it misses, he has little else for a while.",
    "ult_note": "Depth Charge knocks up its target and everyone on the way; respect it after 6.",
    "spike_note": "Strong from level 2 and again at level 6.",
    "notes": "",
}  # fmt: skip
CONTEXT = TraitContext(item_names=frozenset({"Black Cleaver"}))


class FakeAsk:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts: list[tuple[str, str]] = []

    def __call__(self, system: str, prompt: str):
        self.prompts.append((system, prompt))
        answer = self.answers.pop(0)
        return (answer if isinstance(answer, str) else json.dumps(answer)), (100, 50)


def run_draft(static_tables, repo_paths, ask, champ="Nautilus"):
    return draft(champ, static_tables, CONTEXT, repo_paths.root / "docs" / "TRAITS.md", [],
                 ask, "16.19.1")  # fmt: skip


def test_schema_requires_every_field_and_nothing_else():
    assert SCHEMA["additionalProperties"] is False
    assert set(SCHEMA["required"]) == set(SCHEMA["properties"])
    assert SCHEMA["properties"]["early"]["enum"] == [0, 1, 2, 3]


def test_rubric_comes_from_the_traits_doc(repo_paths):
    text = rubric(repo_paths.root / "docs" / "TRAITS.md")
    assert text.startswith("## Columns") and "## Tag vocabulary" in text
    assert "ult_join" in text and "Seeding every champion" not in text


def test_system_prompt_includes_examples(repo_paths):
    example = dict.fromkeys(CHAMPION_TRAITS, "")
    example.update(champ_id="LeeSin", early="3", key_note="example note")
    prompt = system_prompt(repo_paths.root / "docs" / "TRAITS.md", [example])
    assert "example note" in prompt and '"reviewed"' not in prompt


def test_champion_brief(static_tables):
    brief = champion_brief(static_tables, "LeeSin")
    assert brief.startswith("Lee Sin (champ_id: LeeSin)")
    assert "range: melee" in brief and "- R Dragon's Rage (cooldowns 110|85|60):" in brief
    with pytest.raises(DraftError, match="refresh"):
        champion_brief(static_tables, "Nobody")


def test_to_row():
    row = to_row("Nautilus", GOOD)
    assert tuple(row) == CHAMPION_TRAITS
    assert (row["early"], row["spikes"], row["tags"]) == ("3", "2|6", "airborne|ult_engage")
    assert (row["reviewed"], row["source"], row["role"]) == ("n", "llm", "")


def test_draft_first_try(static_tables, repo_paths):
    ask = FakeAsk(GOOD)
    result = run_draft(static_tables, repo_paths, ask)
    assert result.attempts == 1 and (result.input_tokens, result.output_tokens) == (100, 50)
    assert result.row["notes"] == "drafted from 16.19.1 ability text"
    system, prompt = ask.prompts[0]
    assert "## Scales (rubric)" in system and "Nautilus (champ_id: Nautilus)" in prompt


def test_draft_retries_once_with_the_problems(static_tables, repo_paths):
    bad = dict(GOOD, spike_note="Strong once Black Cleaver is done.")
    ask = FakeAsk("not json", dict(GOOD))
    assert run_draft(static_tables, repo_paths, ask).attempts == 2
    assert "wasn't the JSON object" in ask.prompts[1][1]
    ask = FakeAsk(bad, bad)
    with pytest.raises(DraftError, match="failed validation twice"):
        run_draft(static_tables, repo_paths, ask)
    assert "names items (Black Cleaver)" in ask.prompts[1][1]


def test_missing_champions_and_examples(static_tables):
    rows = [dict.fromkeys(CHAMPION_TRAITS, "") | {"champ_id": "LeeSin"}]
    assert missing_champions(static_tables, rows) == ["Elise", "Gnar", "Nautilus"]
    reviewed = rows[0] | {"reviewed": "y"}
    prototype = rows[0] | {"champ_id": "Jhin", "source": "prototype", "ult_note": "x"}
    unfinished = rows[0] | {"champ_id": "Ashe", "source": "prototype"}
    assert example_rows([unfinished, prototype, reviewed]) == [reviewed, prototype]


def test_append_traits_only_appends(tmp_path):
    from scout.paths import Paths

    paths = Paths(tmp_path)
    first = to_row("Nautilus", GOOD)
    write_csv(paths.manual_dir / "champion_traits.csv", CHAMPION_TRAITS, [first])
    before = (paths.manual_dir / "champion_traits.csv").read_text(encoding="utf-8")
    append_traits(paths, [to_row("Leona", GOOD)])
    after = (paths.manual_dir / "champion_traits.csv").read_text(encoding="utf-8")
    assert after.startswith(before)
    assert [r["champ_id"] for r in read_csv(paths.manual_dir / "champion_traits.csv")] == [
        "Nautilus", "Leona"
    ]  # fmt: skip
    with pytest.raises(ValueError, match="already in champion_traits.csv: Leona"):
        append_traits(paths, [to_row("Leona", GOOD)])


# ---------------------------------------------------------------- CLI

runner = CliRunner()


def test_cli_needs_a_champion_or_all_missing(scout_home):
    assert runner.invoke(app, ["draft-traits"]).exit_code == 2
    assert runner.invoke(app, ["draft-traits", "LeeSin", "--all-missing"]).exit_code == 2


def test_cli_explains_a_missing_api_key(scout_home):
    result = runner.invoke(app, ["draft-traits", "LeeSin"])
    assert result.exit_code == 1 and "ANTHROPIC_API_KEY" in result.output


def test_cli_drafts_and_appends(scout_home, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    ask = FakeAsk(GOOD)
    monkeypatch.setattr("scout.cli.anthropic_ask", lambda model, key: ask)
    result = runner.invoke(app, ["draft-traits", "Nautilus"])
    assert result.exit_code == 0, result.output
    assert "Nautilus: drafted (reviewed=n)" in result.output
    rows = read_csv(scout_home.manual_dir / "champion_traits.csv")
    assert [(r["champ_id"], r["source"], r["reviewed"]) for r in rows] == [("Nautilus", "llm", "n")]
    again = runner.invoke(app, ["draft-traits", "Nautilus"])
    assert "already has a traits row" in again.output
