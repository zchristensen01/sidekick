"""Parsers for Data Dragon, CommunityDragon and the LoL wiki, against recorded responses."""

import json

import pytest

from scout.data import cdragon, ddragon, wiki
from scout.model.roles import Role


@pytest.fixture
def sources(repo_paths):
    root = repo_paths.fixtures_dir / "sources"

    def load(name: str):
        text = (root / name).read_text(encoding="utf-8")
        return json.loads(text) if name.endswith(".json") else text

    return load


# ---------------------------------------------------------------- Data Dragon


def test_latest_version_skips_junk_entries():
    assert ddragon.latest_version(["16.19.1", "16.18.1"]) == "16.19.1"
    assert ddragon.latest_version(["lolpatch_3.7", "16.19.1"]) == "16.19.1"
    with pytest.raises(ValueError):
        ddragon.latest_version(["lolpatch_3.7"])


def test_versions_fixture(sources):
    assert ddragon.latest_version(sources("ddragon/versions.json")) == "16.19.1"


def test_parse_champions_and_abilities(sources):
    champions = ddragon.parse_champions(sources("ddragon/championFull_sample.json"))
    assert sorted(champions) == ["Elise", "Gnar", "LeeSin", "Nautilus"]
    lee = champions["LeeSin"]
    assert (lee.key, lee.name, lee.tags) == (64, "Lee Sin", ("Fighter", "Assassin"))
    assert [a.slot for a in lee.abilities] == ["P", "Q", "W", "E", "R"]
    passive, q, *_, r = lee.abilities
    assert (passive.max_rank, passive.cooldowns) == (None, ())
    assert (q.name, q.max_rank, q.cooldowns) == ("Sonic Wave / Resonating Strike", 5,
                                                (10, 9, 8, 7, 6))  # fmt: skip
    assert (r.name, r.cooldowns) == ("Dragon's Rage", (110, 85, 60))
    assert "<br>" not in q.description and "Resonating Strike: Lee Sin dashes" in q.description


def test_parse_champions_drops_mode_only_entries():
    full = {"data": {
        "Jade_LeeSin": {"key": "60064", "name": "Lee Sin", "spells": []},
        "Odd": {"key": "x", "name": "Odd", "spells": []},
        "Annie": {"key": "1", "name": "Annie", "spells": [], "passive": {}},
    }}  # fmt: skip
    assert list(ddragon.parse_champions(full)) == ["Annie"]


def test_clean_text():
    raw = "Deals <magicDamage>damage</magicDamage>.<br><br>Then &amp;  more<br/>text "
    assert ddragon.clean_text(raw) == "Deals damage. Then & more text"
    assert ddragon.clean_text(None) == ""


def test_summoner_spells_are_summoners_rift_only(sources):
    spells = ddragon.parse_summoner_spells(sources("ddragon/summoner.json"))
    by_name = {name: key for key, _, name in spells}
    assert by_name["Smite"] == 11 and by_name["Flash"] == 4 and by_name["Teleport"] == 12
    assert all(isinstance(key, int) for key, _, _ in spells)


def test_items_are_purchasable_on_summoners_rift(sources):
    items = ddragon.parse_items(sources("ddragon/item_sample.json"))
    names = {name for _, name, *_ in items}
    assert {"Boots", "Black Cleaver", "Zhonya's Hourglass"} <= names
    assert "Emberknife" not in names  # not on Summoner's Rift
    assert "Fortification" not in names  # on the map, but you can't buy it
    by_name = {name: (gold, depth, boots) for _, name, gold, depth, boots in items}
    assert by_name["Boots"] == (300, 1, True)
    assert by_name["Black Cleaver"][1] == 3 and not by_name["Black Cleaver"][2]  # finished


# ---------------------------------------------------------------- CommunityDragon


def test_cdragon_champion(sources):
    lee = cdragon.parse_champion(sources("cdragon/champion_64.json"))
    assert (lee.key, lee.champ_id, lee.range_type, lee.damage_type) == (
        64, "LeeSin", "melee", "physical"
    )  # fmt: skip
    assert lee.ratings == {"damage": 3, "durability": 2, "cc": 2, "mobility": 3, "utility": 1,
                           "difficulty": 3}  # fmt: skip
    gnar = cdragon.parse_champion(sources("cdragon/champion_150.json"))
    assert gnar.range_type == "ranged"  # Data Dragon's attack range (175) would say melee
    assert cdragon.parse_champion(sources("cdragon/champion_111.json")).damage_type == "magic"


# ---------------------------------------------------------------- LoL wiki


def test_wiki_module(sources):
    champions = wiki.parse_module(sources("wiki/ChampionData_sample.lua"))
    assert {"Elise", "Gnar", "LeeSin", "Nautilus"} <= set(champions)
    elise = champions["Elise"]
    assert elise.classes == ("diver",) and elise.positions == (Role.JUNGLE,)
    assert (elise.range_type, elise.adaptive_type) == ("ranged", "magic")
    assert elise.last_changed_patch == "16.19"  # "V26.19" in-game numbering
    assert champions["Gnar"].last_changed_patch == "15.16"
    assert champions["Nautilus"].positions == (Role.SUPPORT,)
    assert champions["LeeSin"].ratings["difficulty"] == 3
    assert (elise.attack_range, champions["Gnar"].attack_range) == (550, 175)
    assert champions["LeeSin"].move_speed is not None


def test_wiki_duplicates_keep_the_first_entry():
    text = """return {
      ["Kled"] = {["apiname"] = "Kled", ["role"] = {"Diver"}},
      ["Kled & Skaarl"] = {["apiname"] = "Kled", ["role"] = {"Vanguard"}},
    }"""
    assert wiki.parse_module(text)["Kled"].classes == ("diver",)


def test_wiki_positions_map_to_roles_and_report_unknown_labels():
    text = """return {["X"] = {["apiname"] = "X", ["client_positions"] = {"Middle", "Bottom"},
               ["external_positions"] = {"Support", "Roaming"}}}"""
    x = wiki.parse_module(text)["X"]
    assert x.positions == (Role.MID, Role.BOT, Role.SUPPORT)
    assert x.unknown_positions == ("Roaming",)


def test_lua_reader():
    text = """-- comment
    --[[ block
    comment ]]
    return {
      a = -2*(3+1), b = 84+1000/17, c = 1.5e1, d = "q\\"uote", e = 'single',
      f = {"x", "y"}, g = {[1] = "one", [2] = "two"}, h = {["k"] = true, n = nil},
      i = {}, -- trailing comment
    }"""
    value = wiki.parse_lua_return(text)
    assert value["a"] == -8 and value["b"] == pytest.approx(142.8235) and value["c"] == 15.0
    assert (value["d"], value["e"]) == ('q"uote', "single")
    assert value["f"] == ["x", "y"] and value["g"] == ["one", "two"]
    assert value["h"] == {"k": True, "n": None} and value["i"] == {}


@pytest.mark.parametrize("text", ["{1}", "return {1, 2", "return {a = os.exit()}", "return @"])
def test_lua_reader_rejects_anything_but_data(text):
    with pytest.raises(wiki.LuaParseError):
        wiki.parse_lua_return(text)


def test_wiki_mechanics_from_page_categories(sources):
    """Category names come from the wiki's own 'Advanced attributes' list, read at refresh."""
    attributes = wiki.parse_attributes(sources("wiki/attributes.json"))
    assert {"knockup", "knockback", "knock_aside", "pull", "dash", "blink", "stealth"} <= attributes
    assert not {"mana", "melee", "ranged"} & attributes  # resources and range aren't mechanics
    pages, cont = wiki.parse_categories(sources("wiki/categories_sample.json"))
    assert cont is None and set(pages) == {"Elise", "Gnar", "Lee Sin", "Nautilus"}
    assert wiki.mechanics(pages["Gnar"], attributes) == (
        "dash", "haste", "knockback", "shapeshifter", "slow", "stun")
    redirected, _ = wiki.parse_categories(sources("wiki/categories_redirect.json"))
    assert "Nunu & Willump" in redirected  # the wiki's page is "Nunu"; we keep the asked title
    assert "knockup" in wiki.mechanics(redirected["Nunu & Willump"], attributes)
    assert wiki.mechanic_name("Category:Knock aside champion") == "knock_aside"
    assert wiki.mechanic_name("Category:Champions with critical strike ratios") is None


def test_split_tips_are_joined_back():
    """Riot's data splits a few tips around a keyword (Illaoi, Quinn on 16.19); whole tips
    with a trailing space or no full stop stay separate."""
    illaoi = ["Tentacles are an immense source of power. Don't fight without them.",
              "Spirits inherit their target's current health. If making a ", "Vessel",
              " is your goal, try whittling your opponent's health down a bit first.",
              "Leap of Faith is best used to follow-up a strong engage. "]  # fmt: skip
    joined = ddragon.tips(illaoi)
    assert len(joined) == 3
    assert joined[1].startswith("Spirits inherit their target's current health. If making a ")
    assert "a Vessel is your goal, try whittling" in joined[1]
    whole = ["Spider Form finishes off enemies with low health. ", "Spiderlings attack. ",
             "Shield is consumed for health", "Use spells to escape once inside"]  # fmt: skip
    assert len(ddragon.tips(whole)) == 4
