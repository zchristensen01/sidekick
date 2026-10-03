"""M23: History, past games kept on this PC (reports/, gitignored)."""

from scout.data.store import write_csv
from scout.postgame.history import POSTGAME
from scout.report import past

VIEW = {"screen": "report", "phase": "final", "written": True,
        "header": {"role": "jungle", "champion": "Jax", "champion_id": "Jax",
                   "patch": "26.19"},
        "opponents": [{"id": "Ambessa", "name": "Ambessa"}], "kits": []}  # fmt: skip


def postgame_rows(report: str) -> list[dict[str, str]]:
    rows = []
    for kind, hit in (("lane_winner", "y"), ("priority", "n"), ("gank_lane", "")):
        row = dict.fromkeys(POSTGAME, "")
        row.update(report=report, kind=kind, predicted="us", actual="us", hit=hit,
                   measure="gold difference at 15: +820")  # fmt: skip
        rows.append(row)
    return rows


def test_games_are_listed_newest_first_with_the_post_game_check(tmp_path):
    reports, history = tmp_path / "reports", tmp_path / "history"
    reports.mkdir()
    new = reports / "2026-01-02_201500_jungle_Jax.md"
    new.write_text("# Final report", encoding="utf-8")
    past.save(new, VIEW, {"saved_at": "2026-01-02T20:15:40", "account": "Player#NA1"})
    (reports / "2026-01-01_140000_support_Sona.md").write_text("# Old report", encoding="utf-8")
    (reports / "notes.md").write_text("not a report", encoding="utf-8")  # not the watcher's name
    write_csv(history / "postgame.csv", POSTGAME, postgame_rows(new.stem))

    games = past.listing(reports, history / "postgame.csv")
    assert [g["id"] for g in games] == [new.stem, "2026-01-01_140000_support_Sona"]
    first, old = games
    assert first["kind"] == "screen" and first["account"] == "Player#NA1" and first["written"]
    assert first["opponents"] == [{"id": "Ambessa", "name": "Ambessa"}]
    assert first["postgame"] == {"graded": 2, "hits": 1}  # the ungradable one doesn't count
    assert old["kind"] == "text" and old["at"] == "2026-01-01T14:00:00" and old["postgame"] is None

    one = past.game(reports, history / "postgame.csv", new.stem)
    assert one["view"] == VIEW and [r["hit"] for r in one["results"]] == ["y", "n", ""]
    assert past.game(reports, history / "postgame.csv", old["id"])["text"] == "# Old report"
    for bad in ("../secrets", "notes", "2026-01-02_201500_jungle_Nope"):
        assert past.game(reports, history / "postgame.csv", bad) is None


def test_the_app_lists_and_opens_past_games(scout_home):
    from scout.app.main import App

    reports = scout_home.reports_dir()
    reports.mkdir(parents=True, exist_ok=True)
    report = reports / "2026-01-02_201500_jungle_Jax.md"
    report.write_text("# Final report", encoding="utf-8")
    past.save(report, VIEW, {"saved_at": "2026-01-02T20:15:40", "account": "Player#NA1"})
    app = App(scout_home)
    listed = app.action("history", {})
    assert [g["id"] for g in listed["games"]] == [report.stem]
    assert listed["accounts"] == ["Player#NA1"]
    assert app.action("history_game", {"id": report.stem})["view"]["phase"] == "final"
    assert "error" in app.action("history_game", {"id": "../../.env"})
