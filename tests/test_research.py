"""The research prompts (`scout research`) and reading the agents' replies back in
(`scout import-research`): only the text prompts are left (M19); everything an agent needs is
inside each prompt; replies are recognized by their table, checked, and applied only on OK."""

from datetime import UTC, datetime
from pathlib import Path

from scout import research_import
from scout.data.store import read_csv, write_csv
from scout.research import champions, prompts

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
FACTS = [{"fact_id": "baron_timer", "topic": "objective", "role": "",
          "text": "Baron Nashor spawns at 20:00.", "source": "Riot: Patch 26.1 notes",
          "source_url": "https://example.invalid/patch-26-1", "patch": "26.1",
          "checked_on": "2026-10-03"}]  # fmt: skip
FACT_COLUMNS = ("fact_id", "topic", "role", "text", "source", "source_url", "patch", "checked_on")


def test_only_the_text_prompts_are_left_and_carry_their_data(static_tables):
    champs = champions(static_tables)
    files = prompts(champs, FACTS, "16.19.1")
    assert set(files) == {"README.md", "patch_notes.md", "game_facts.md", "class_definitions.md"}
    for name, text in files.items():
        if name != "README.md":
            assert "## Prompt" in text and "## What to send back" in text, name
            assert "No ratings of your own" in text and "Only what you saw" in text, name
    for c in champs:  # the patch notes prompt carries every champion id
        assert f"| {c.n} | {c.champ_id} | {c.name} |" in files["patch_notes.md"]
    for name in ("patch_notes.md", "game_facts.md"):
        assert "Baron Nashor spawns at 20:00." in files[name]  # today's facts, to compare
    assert "Vanguard" in files["class_definitions.md"]
    assert "scout import-research" in files["README.md"]


def reply(tmp, name: str, body: str):
    folder = tmp.root / "research" / "results"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(body, encoding="utf-8")
    return folder / name


def test_replies_are_read_by_their_table_checked_and_applied(scout_home):
    write_csv(scout_home.manual_dir / "game_facts.csv", FACT_COLUMNS, FACTS)
    reply(scout_home, "anything.md", """BATCH: whatever
```csv
champ_id,patch,what_changed,quote
Elise,26.20,"Q (Neurotoxin) damage","Q - Neurotoxin: damage 40 => 45"
NotAChamp,26.20,something,"a quote"
```
Then:
```csv
fact_id,topic,role,text,source,source_url,patch,checked_on
baron_timer,objective,,Baron Nashor spawns at 25:00.,Riot: Patch 26.20 notes,https://example.invalid/26-20,26.20,2026-10-20
herald_timer,objective,,The Rift Herald spawns at 15:00.,somewhere,not-a-link,26.20,2026-10-20
```
SOURCES:
https://example.invalid/26-20
""")
    reply(scout_home, "classes.md", """```csv
class,quote,source,source_url
Vanguard,"Vanguards are ... (Riot's words)",Riot: champion classes,https://example.invalid/classes
```""")
    champs = [r["champ_id"] for r in read_csv(scout_home.static_dir("16.19.1") / "champions.csv")]
    plan = research_import.plan(scout_home, champs, NOW)
    text = "\n".join(plan.lines())
    assert "unknown champion id 'NotAChamp'" in text and "no source or no https link" in text
    assert [r["champ_id"] for r in plan.review_rows] == ["Elise"]
    assert [new["text"] for _, new in plan.facts_changed] == ["Baron Nashor spawns at 25:00."]
    assert not plan.facts_added  # the herald row had no real link: not applied
    assert [r["class"] for r in plan.classes] == ["Vanguard"]
    assert read_csv(scout_home.manual_dir / "game_facts.csv")[0]["text"].endswith("20:00.")
    done = research_import.apply(scout_home, plan)  # only after the owner's OK (the command asks)
    assert done[0].startswith("review queue: +1")
    assert read_csv(scout_home.manual_dir / "game_facts.csv")[0]["text"].endswith("25:00.")
    assert read_csv(scout_home.manual_dir / "class_definitions.csv")[0]["class"] == "Vanguard"
    assert (scout_home.root / "research" / "results" / "done" / "anything.md").exists()
    assert research_import.plan(scout_home, champs, NOW).empty  # nothing left to apply


def test_the_full_game_facts_check_beats_a_patch_notes_row(scout_home):
    """Both replies have the same fact: the game facts reply re-checked every fact in full, the
    patch notes reply only what that patch changed, so the full check's row is kept."""
    write_csv(scout_home.manual_dir / "game_facts.csv", FACT_COLUMNS, FACTS)
    reply(scout_home, "a_game_facts.md", """```csv
fact_id,topic,role,text,source,source_url,patch,checked_on
baron_timer,objective,,"Baron Nashor spawns at 20:00, and more.",Riot: Patch 26.1 notes,https://example.invalid/full,26.19,2026-10-03
```""")
    reply(scout_home, "z_patch_notes.md", """```csv
champ_id,patch,what_changed,quote
Elise,26.19,W attack speed,"W - Skittering Frenzy: 60% => 70%"
```
```csv
fact_id,topic,role,text,source,source_url,patch,checked_on
baron_timer,objective,,Baron's timer part only.,Riot: Patch 26.19 notes,https://example.invalid/part,26.19,2026-10-03
```""")
    champs = [r["champ_id"] for r in read_csv(scout_home.static_dir("16.19.1") / "champions.csv")]
    plan = research_import.plan(scout_home, champs, NOW)
    kept = [new["text"] for _, new in plan.facts_changed]
    assert kept == ["Baron Nashor spawns at 20:00, and more."]
    assert any("kept the game facts check's row" in line for line in plan.lines())
    research_import.apply(scout_home, plan, "16.19")
    assert research_import.due(scout_home, "16.19") == ["class_definitions"]  # both marked done


def test_research_due_follows_the_patch(scout_home):
    assert research_import.due(scout_home, "16.19") == ["patch_notes", "game_facts",
                                                        "class_definitions"]  # fmt: skip
    research_import.record_done(scout_home, ["patch_notes", "game_facts"], "16.19", "2026-10-04")
    assert research_import.due(scout_home, "16.19") == ["class_definitions"]
    assert research_import.due(scout_home, "16.20") == ["patch_notes", "game_facts",
                                                        "class_definitions"]  # fmt: skip
    research_import.record_done(scout_home, ["class_definitions"], "16.19", "2026-10-04")
    assert research_import.due(scout_home, "16.19") == []  # class definitions: once


def test_the_app_shows_whats_due(scout_home):
    from scout.app.main import App

    app = App(scout_home)
    meta = app.meta()
    assert meta["research"]["prompts"] == ["patch_notes", "game_facts", "class_definitions"]
    assert meta["research"]["remind"] is False  # a new install: the top bar stays quiet
    assert meta["update"] is None  # nothing checked yet
    assert app.action("set_research_reminders", {"on": True}) == {"ok": True}
    assert app.meta()["research"]["remind"] is True  # the PC that runs the research


def test_the_app_refreshes_its_data_every_6_hours(scout_home):
    import time

    from scout.app.main import REFRESH_EVERY_S, App
    from scout.app.update import refreshed_file

    app = App(scout_home)
    now = time.time()
    assert app.refresh_due(idle=True, now=now)  # never refreshed by the app
    assert not app.refresh_due(idle=False, now=now)  # never in champ select or a game
    stamp = refreshed_file(scout_home)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    assert not app.refresh_due(idle=True, now=time.time())
    assert app.refresh_due(idle=True, now=time.time() + REFRESH_EVERY_S)
    app.job = "Updating"
    assert not app.refresh_due(idle=True, now=time.time() + REFRESH_EVERY_S)


WIKI = Path(__file__).resolve().parent / "fixtures" / "sources" / "wiki"


def test_mid_patch_updates_are_read_from_the_wikis_patch_page():
    import json

    from scout.data.patch_updates import parse_updates

    def load(name):
        return json.loads((WIKI / name).read_text(encoding="utf-8"))

    assert parse_updates(load("patch_page_sections_26_19.json")) == ["October 2nd Queue Update"]
    assert parse_updates(load("patch_page_sections_26_10.json")) == ["May 14th Hotfix"]
    assert parse_updates(load("patch_page_missing.json")) == []


class PageFetcher:
    def __init__(self, raw):
        self.raw, self.urls = raw, []

    def json(self, url, cache=None, *, refresh=False):
        self.urls.append(url)
        return self.raw


def test_a_new_hotfix_makes_the_patch_notes_due_again_with_a_prompt_about_it(scout_home):
    import json

    from scout.data import patch_updates
    from scout.research import regenerate

    sections = json.loads((WIKI / "patch_page_sections_26_19.json").read_text(encoding="utf-8"))
    fetcher = PageFetcher(sections)
    found = patch_updates.check(scout_home, fetcher, "16.19.1", NOW)
    assert found.updates == ["October 2nd Queue Update"] and "page=V26.19" in fetcher.urls[0]
    research_import.record_done(scout_home, ["patch_notes", "game_facts", "class_definitions"],
                                "16.19", "2026-10-03")  # fmt: skip
    status = read_csv(research_import.status_file(scout_home))
    assert [r["covered"] for r in status if r["prompt"] == "patch_notes"] == [
        "October 2nd Queue Update"]  # what the round was asked about
    assert research_import.due(scout_home, "16.19") == []
    written = {p.name for p in regenerate(scout_home)}
    assert "patch_notes.md" in written and not regenerate(scout_home)  # unchanged: not rewritten
    full = (scout_home.root / "research" / "patch_notes.md").read_text(encoding="utf-8")
    assert "<PATCH" not in full and '"Patch 26.19 Notes"' in full

    sections["parse"]["sections"].insert(-2, {"level": "2", "line": "Hotfixes"})
    sections["parse"]["sections"].insert(-2, {"level": "3", "line": "October 9th Hotfix"})
    patch_updates.check(scout_home, PageFetcher(sections), "16.19.1", NOW)
    assert research_import.new_updates(scout_home, "16.19") == ["October 9th Hotfix"]
    assert research_import.due(scout_home, "16.19") == ["patch_notes"]
    assert [p.name for p in regenerate(scout_home)] == ["patch_notes.md"]
    hotfix = (scout_home.root / "research" / "patch_notes.md").read_text(encoding="utf-8")
    assert "- October 9th Hotfix" in hotfix
    assert "Report only the changes these updates make" in hotfix
    assert "October 2nd Queue Update" not in hotfix.split("## Prompt")[1].split("Table A")[0]

    research_import.record_done(scout_home, ["patch_notes"], "16.19", "2026-10-10")
    assert research_import.due(scout_home, "16.19") == []  # the hotfix round covered it
    assert research_import.due(scout_home, "16.20") == ["patch_notes", "game_facts"]


def test_no_wiki_page_yet_is_not_a_hotfix(scout_home):
    import json

    from scout.data import patch_updates

    missing = json.loads((WIKI / "patch_page_missing.json").read_text(encoding="utf-8"))
    found = patch_updates.check(scout_home, PageFetcher(missing), "16.20.1", NOW)
    assert found.updates == [] and "doesn't exist" in found.note
    assert research_import.new_updates(scout_home, "16.20") == []
