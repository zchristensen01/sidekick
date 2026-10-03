"""`scout review`: order of the walk, accept, edit, skip, quit, and what gets saved."""

import json
from datetime import UTC, datetime

from lcu_fakes import make_champ_select_session

from scout.data import review
from scout.data.schemas import CHAMPION_TRAITS
from scout.data.store import TraitContext, read_csv, save_traits
from scout.reviewing import Session, recent_champions, review_order

NOW = datetime(2026, 10, 3, 20, 0, tzinfo=UTC)


def trait_row(champ: str, **changes) -> dict[str, str]:
    row = dict.fromkeys(CHAMPION_TRAITS, "")
    row.update(
        champ_id=champ, early="2", engage="2", cc="2", escape="1", scaling="2", roam="1",
        waveclear="2", frontline="1", spikes="6", tags="", key_note="A key note.",
        ult_note="An ult note.", spike_note="Stronger at level 6.", reviewed="n", source="llm",
    )  # fmt: skip
    row.update(changes)
    return row


def test_order_is_recent_games_then_pool_then_the_rest():
    rows = [trait_row(c) for c in ("Ahri", "Elise", "LeeSin", "Zed", "Gnar")]
    rows[4]["reviewed"] = "y"  # Gnar is done
    queue = [review.entry("Gnar", "abilities_changed", "slots R", "16.19.1", NOW)]
    items = review_order(rows, queue, recent=["Zed", "Gnar"], pool=["Elise", "LeeSin"])
    assert [(i.champ_id, i.group) for i in items] == [
        ("Zed", "recent game"), ("Gnar", "recent game"),
        ("Elise", "your pool"), ("LeeSin", "your pool"), ("Ahri", "other"),
    ]  # fmt: skip
    assert items[1].reasons == ["abilities_changed: slots R"]
    assert items[0].reasons == ["unreviewed (llm)"]
    only = review_order(rows, queue, [], [], only="Ahri")
    assert [i.champ_id for i in only] == ["Ahri"]
    assert review_order(rows, queue, [], [], only="Nobody") == []


def test_recent_champions_from_recordings(tmp_path):
    for name, champ in (("2026-10-01_a.json", 64), ("2026-10-02_b.json", 60)):
        session = make_champ_select_session(my_champ=champ, enemy_champs=(150, 0, 0, 0, 0))
        (tmp_path / name).write_text(json.dumps({"snapshots": [{"session": session}]}), "utf-8")
    (tmp_path / "2026-10-03_broken.json").write_text("{", encoding="utf-8")
    by_key = {64: "LeeSin", 60: "Elise", 150: "Gnar", 86: "Garen"}
    assert recent_champions(tmp_path, by_key) == ["Garen", "Elise", "Gnar", "LeeSin"]


class Script:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.questions: list[str] = []

    def __call__(self, question: str) -> str:
        self.questions.append(question)
        return self.answers.pop(0)


def make_session(paths, static_tables, answers: Script, messages: list[str]) -> Session:
    return Session(paths=paths, version="16.19.1", tables=static_tables,
                   context=TraitContext(), ask=answers, echo=messages.append,
                   now=lambda: NOW)  # fmt: skip


def test_accept_marks_reviewed_and_resolves_the_queue(scout_home, static_tables):
    rows = [trait_row("LeeSin"), trait_row("Elise")]
    save_traits(scout_home, rows)
    review.add(scout_home.review_queue, [review.entry("LeeSin", "patch_changed", "", "x", NOW)])
    items = review_order(rows, review.open_entries(scout_home.review_queue), [], [])
    messages: list[str] = []
    answers = Script("s", "a")  # Elise comes first (alphabetical): skip it, accept Lee Sin
    saved = make_session(scout_home, static_tables, answers, messages).run(rows, items)
    assert saved == 1
    stored = {r["champ_id"]: r for r in read_csv(scout_home.manual_dir / "champion_traits.csv")}
    assert (stored["Elise"]["reviewed"], stored["LeeSin"]["reviewed"]) == ("n", "y")
    # accepted as is: reviewed, but still the drafted row, so Riot's ratings keep filling cc,
    # escape and frontline (only a row the owner changes becomes source=owner)
    assert (stored["LeeSin"]["source"], stored["LeeSin"]["reviewed_patch"]) == ("llm", "16.19.1")
    assert stored["LeeSin"]["key_note"] == "A key note."  # nothing else changed
    assert review.open_entries(scout_home.review_queue) == []
    assert any("Dragon's Rage" in m for m in messages)  # the ability text was shown


def test_incomplete_row_must_be_edited_before_saving(scout_home, static_tables):
    rows = [trait_row("Elise", source="prototype", roam="", ult_note="")]
    save_traits(scout_home, rows)
    items = review_order(rows, [], [], [])
    edits = [""] * len(("early", "engage", "cc", "escape", "scaling"))
    # roam, waveclear, frontline, spikes, tags, style, key_note, ult_note, spike_note, notes
    edits += ["2", "", "", "", "", "", "", "Cocoon can be dodged.", "", "-"]
    answers = Script("a", "e", *edits, "y")
    messages: list[str] = []
    saved = make_session(scout_home, static_tables, answers, messages).run(rows, items)
    assert saved == 1
    assert any("Can't accept as is" in m and "roam is empty" in m for m in messages)
    stored = read_csv(scout_home.manual_dir / "champion_traits.csv")[0]
    assert (stored["roam"], stored["ult_note"], stored["notes"]) == (
        "2",
        "Cocoon can be dodged.",
        "",
    )
    assert (stored["reviewed"], stored["source"]) == ("y", "owner")


def test_invalid_edit_and_declined_save_change_nothing(scout_home, static_tables):
    rows = [trait_row("LeeSin")]
    save_traits(scout_home, rows)
    before = (scout_home.manual_dir / "champion_traits.csv").read_text(encoding="utf-8")
    bad = ["9"] + [""] * 14  # early=9 is out of range
    keep = [""] * 15
    answers = Script("e", *bad, "e", *keep, "n", "q")
    messages: list[str] = []
    saved = make_session(scout_home, static_tables, answers, messages).run(
        rows, review_order(rows, [], [], [])
    )
    assert saved == 0
    assert any("early must be 0-3" in m for m in messages)
    assert (scout_home.manual_dir / "champion_traits.csv").read_text(encoding="utf-8") == before
