"""The static build and `scout refresh --static`, offline against recorded source responses."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scout.data import cdragon, ddragon, refresh, static, wiki
from scout.data.fetch import NotFound
from scout.data.schemas import CHAMPION_OVERRIDES, CHAMPION_TRAITS, STATIC_FILES
from scout.data.store import read_csv, write_csv
from scout.paths import Paths

SOURCES = Path(__file__).parent / "fixtures" / "sources"
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def load(name: str):
    text = (SOURCES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


class FakeFetcher:
    """Serves recorded responses by URL. Unknown URLs are 404s, like the real servers."""

    def __init__(self, version: str = "16.19.1", full=None):
        self.version = version
        folder = ".".join(version.split(".")[:2])
        self.responses = {
            ddragon.VERSIONS_URL: [version, "16.18.1"],
            ddragon.champion_full_url(version): full or load("ddragon/championFull_sample.json"),
            ddragon.summoner_url(version): load("ddragon/summoner.json"),
            ddragon.item_url(version): load("ddragon/item_sample.json"),
            cdragon.metadata_url(folder): load("cdragon/content-metadata.json"),
            wiki.URL: load("wiki/ChampionData_sample.lua"),
            wiki.attributes_url(): load("wiki/attributes.json"),
            wiki.categories_url(["Elise", "Gnar", "Lee Sin", "Nautilus"]):
                load("wiki/categories_sample.json"),
        }
        for key in (60, 64, 111, 150):
            self.responses[cdragon.champion_url(folder, key)] = load(f"cdragon/champion_{key}.json")
        self.calls: list[str] = []

    def json(self, url, cache=None, *, refresh=False):
        return copy.deepcopy(self._get(url))

    def text(self, url, cache=None, *, refresh=False):
        return self._get(url)

    def _get(self, url):
        self.calls.append(url)
        if url not in self.responses:
            raise NotFound(f"{url}: HTTP 404")
        return self.responses[url]


@pytest.fixture
def paths(tmp_path) -> Paths:
    paths = Paths(tmp_path)
    paths.manual_dir.mkdir(parents=True)
    write_csv(paths.manual_dir / "champion_traits.csv", CHAMPION_TRAITS, [
        {"champ_id": "Elise", "role": "jungle"}, {"champ_id": "Nautilus", "role": "support"},
    ])  # fmt: skip
    write_csv(paths.manual_dir / "champion_overrides.csv", CHAMPION_OVERRIDES, [])
    return paths


def sources_for(fetcher: FakeFetcher) -> dict:
    full = fetcher.json(ddragon.champion_full_url(fetcher.version))
    cd = [cdragon.parse_champion(load(f"cdragon/champion_{k}.json")) for k in (60, 64, 111, 150)]
    return {
        "champions": ddragon.parse_champions(full),
        "summoner_spells": ddragon.parse_summoner_spells(load("ddragon/summoner.json")),
        "items": ddragon.parse_items(load("ddragon/item_sample.json")),
        "cdragon": {c.champ_id: c for c in cd},
        "wiki": wiki.parse_module(load("wiki/ChampionData_sample.lua")),
        "mechanics": refresh._wiki_mechanics(fetcher, Path("unused"), ddragon.parse_champions(full),
                                             False),  # fmt: skip
    }


# ---------------------------------------------------------------- build


def test_build_merges_every_source():
    built = static.build("16.19.1", overrides=[], **sources_for(FakeFetcher()))
    assert static.validate(built) == []
    assert built.disagreements == []
    assert built.missing == {"cdragon": [], "wiki": [], "wiki_mechanics": []}
    meta = {row["champ_id"]: row for row in built.tables["champion_meta.csv"]}
    assert meta["Gnar"]["range_type"] == "ranged"  # from CommunityDragon, not attack range
    assert meta["Elise"]["classes"] == "diver" and meta["Elise"]["positions"] == "jungle"
    assert meta["LeeSin"]["legacy_tags"] == "fighter|assassin"
    assert meta["Nautilus"]["damage_type"] == "magic"
    assert meta["LeeSin"]["last_changed_patch"] == "16.12"
    assert (meta["Gnar"]["attack_range"], meta["Elise"]["attack_range"]) == ("175", "550")
    assert meta["LeeSin"]["field_sources"] == (
        "range_type:cdragon|attack_range:wiki|move_speed:wiki|damage_type:cdragon|classes:wiki|"
        "legacy_tags:ddragon|"
        "positions:wiki|client_positions:wiki|mechanics:wiki|last_changed_patch:wiki|"
        "ratings:cdragon"
    )
    assert meta["Nautilus"]["mechanics"] == "dash|knockup|pull|root|shield|slow|stun"
    for name, columns in STATIC_FILES.items():
        assert all(tuple(row) == columns for row in built.tables[name]), name
    abilities = [r for r in built.tables["abilities.csv"] if r["champ_id"] == "LeeSin"]
    assert [(r["slot"], r["cooldowns"]) for r in abilities] == [
        ("P", ""), ("Q", "10|9|8|7|6"), ("W", "7|7|7|7|7"), ("E", "8|8|8|8|8"),
        ("R", "110|85|60"),
    ]  # fmt: skip


def test_build_falls_back_to_the_wiki_and_reports_missing_sources():
    sources = sources_for(FakeFetcher())
    del sources["cdragon"]["Gnar"]
    del sources["wiki"]["Elise"]
    built = static.build("16.19.1", overrides=[], **sources)
    meta = {row["champ_id"]: row for row in built.tables["champion_meta.csv"]}
    assert meta["Gnar"]["range_type"] == "ranged"  # the wiki says ranged too
    assert "range_type:wiki" in meta["Gnar"]["field_sources"]
    assert meta["Elise"]["classes"] == "" and meta["Elise"]["positions"] == ""
    assert built.missing == {"cdragon": ["Gnar"], "wiki": ["Elise"], "wiki_mechanics": []}
    assert static.validate(built) == []  # missing pieces are warnings, not failures


def test_range_disagreement_is_recorded():
    sources = sources_for(FakeFetcher())
    gnar = sources["cdragon"]["Gnar"]
    sources["cdragon"]["Gnar"] = cdragon.CdChampion(gnar.key, gnar.champ_id, "melee",
                                                   gnar.damage_type, gnar.ratings)  # fmt: skip
    built = static.build("16.19.1", overrides=[], **sources)
    assert built.disagreements == [
        {"champ_id": "Gnar", "field": "range_type", "details": "cdragon=melee, wiki=ranged"}
    ]


def test_overrides_win_and_are_marked():
    overrides = [
        {"champ_id": "Gnar", "field": "positions", "value": "top|mid", "reason": "test"},
        {"champ_id": "Gnar", "field": "champ_id", "value": "X", "reason": "not allowed"},
        {"champ_id": "Nobody", "field": "positions", "value": "top", "reason": "unknown"},
    ]
    built = static.build("16.19.1", overrides=overrides, **sources_for(FakeFetcher()))
    gnar = next(r for r in built.tables["champion_meta.csv"] if r["champ_id"] == "Gnar")
    assert gnar["positions"] == "top|mid"
    assert gnar["field_sources"].endswith("positions:override")
    assert "positions:wiki" not in gnar["field_sources"].split("|")
    assert len(built.warnings) == 2


def test_validate_catches_broken_builds():
    built = static.build("16.19.1", overrides=[], **sources_for(FakeFetcher()))
    built.tables["champions.csv"][1]["key"] = built.tables["champions.csv"][0]["key"]
    built.tables["summoner_spells.csv"] = []
    errors = static.validate(built)
    assert any("duplicate champion keys" in e for e in errors)
    assert "no summoner spells" in errors


# ---------------------------------------------------------------- scout refresh --static


def test_refresh_builds_everything_then_does_nothing(paths):
    result = refresh.refresh_static(paths, FakeFetcher(), now=lambda: NOW)
    assert result.built and result.errors == []
    assert paths.patch_file.read_text(encoding="utf-8") == "16.19.1\n"
    folder = paths.static_dir("16.19.1")
    for name, columns in STATIC_FILES.items():
        rows = read_csv(folder / name)
        assert rows and tuple(rows[0]) == columns
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["patch"] == "26.19" and manifest["rows"]["champions.csv"] == 4

    queue = read_csv(paths.review_queue)
    reasons = {(r["champ_id"], r["reason"]) for r in queue}
    assert reasons == {
        ("Gnar", "traits_missing"), ("LeeSin", "traits_missing"),  # no traits rows
        ("Elise", "patch_changed"),  # has traits, and the wiki says it changed this patch
    }  # fmt: skip
    log = paths.refresh_log.read_text(encoding="utf-8")
    assert "## 2026-10-02 12:00 static 16.19.1 (patch 26.19)" in log

    second = FakeFetcher()
    again = refresh.refresh_static(paths, second, now=lambda: NOW)
    assert not again.built and "up to date" in again.message
    assert second.calls == [ddragon.VERSIONS_URL]  # only the version check
    assert len(read_csv(paths.review_queue)) == len(queue)


def test_new_version_diff_goes_to_the_review_queue(paths):
    refresh.refresh_static(paths, FakeFetcher(), now=lambda: NOW)
    full = load("ddragon/championFull_sample.json")
    full["version"] = "16.20.1"
    full["data"]["Nautilus"]["spells"][3]["description"] = "A brand new ultimate."
    full["data"]["Newchamp"] = copy.deepcopy(full["data"]["Gnar"])
    full["data"]["Newchamp"].update(id="Newchamp", key="999", name="Newchamp")
    result = refresh.refresh_static(paths, FakeFetcher("16.20.1", full), now=lambda: NOW)
    assert result.built
    assert any("not in CommunityDragon yet: Newchamp" in w for w in result.warnings)
    added = {(r["champ_id"], r["reason"], r["details"]) for r in result.review_added}
    assert ("Newchamp", "new_champion", "") in added
    assert ("Newchamp", "class_missing", "not in the wiki") in added
    assert ("Nautilus", "abilities_changed", "slots R") in added
    assert not any(r[0] == "Gnar" for r in added)  # already queued for 16.19.1
    assert paths.patch_file.read_text(encoding="utf-8") == "16.20.1\n"


def test_failed_validation_keeps_the_previous_version(paths):
    refresh.refresh_static(paths, FakeFetcher(), now=lambda: NOW)
    full = load("ddragon/championFull_sample.json")
    full["data"]["Gnar"]["key"] = full["data"]["Elise"]["key"]  # duplicate key
    result = refresh.refresh_static(paths, FakeFetcher("16.20.1", full), now=lambda: NOW)
    assert not result.built and result.errors
    assert paths.patch_file.read_text(encoding="utf-8") == "16.19.1\n"
    assert not paths.static_dir("16.20.1").exists()
    assert "Error: duplicate champion keys" in paths.refresh_log.read_text(encoding="utf-8")


def test_missing_cdragon_folder_falls_back_to_latest(paths):
    fetcher = FakeFetcher()
    for url in list(fetcher.responses):
        if "communitydragon" in url:
            fetcher.responses[url.replace("/16.19/", "/latest/")] = fetcher.responses.pop(url)
    result = refresh.refresh_static(paths, fetcher, now=lambda: NOW)
    assert result.built
    assert "CommunityDragon has no 16.19/ folder yet; used latest/" in result.warnings


def test_wiki_is_rechecked_once_three_days_later(paths):
    refresh.refresh_static(paths, FakeFetcher(), now=lambda: NOW)
    two_days = refresh.refresh_static(paths, FakeFetcher(), now=lambda: NOW + timedelta(days=2))
    assert not two_days.built
    later = refresh.refresh_static(paths, FakeFetcher(), now=lambda: NOW + timedelta(days=3))
    assert later.built and later.message.startswith("Re-checked the wiki")
    once = refresh.refresh_static(paths, FakeFetcher(), now=lambda: NOW + timedelta(days=4))
    assert not once.built


def test_prune_keeps_the_newest_three(paths):
    for version in ("16.15.1", "16.16.1", "16.17.1", "16.18.1", "16.9.1"):
        (paths.generated_dir / "static" / version).mkdir(parents=True)
        (paths.cache_dir / "ddragon" / version).mkdir(parents=True)
    removed = {p.name for p in refresh.prune(paths)}
    assert removed == {"16.15.1", "16.9.1"}  # versions compare as numbers, not text
    assert {p.name for p in (paths.generated_dir / "static").iterdir()} == {
        "16.16.1", "16.17.1", "16.18.1"
    }  # fmt: skip
