"""champion_traits.csv validation and lookup (docs/TRAITS.md)."""

import pytest

from scout.data.schemas import CHAMPION_TRAITS
from scout.data.store import (
    TraitContext,
    parse_traits,
    read_csv,
    traits_for,
    validate_traits,
)
from scout.model.roles import Role

CONTEXT = TraitContext(
    champions=frozenset({"Leona", "LeeSin", "Darius"}),
    ability_numbers={
        "Leona": frozenset({"2", "1.5"}),
        "LeeSin": frozenset({"3"}),
        "Darius": frozenset({"5"}),
    },
    ability_names={"Leona": frozenset({"Eclipse", "Zenith Blade", "Solar Flare"})},
    item_names=frozenset({"Eclipse", "Black Cleaver", "Boots"}),
)


def row(**changes) -> dict[str, str]:
    base = dict.fromkeys(CHAMPION_TRAITS, "")
    base.update(
        champ_id="Leona", early="3", engage="3", cc="3", escape="0", scaling="1", roam="1",
        waveclear="1", frontline="3", spikes="2|6", tags="airborne|ult_engage",
        key_note="E (Zenith Blade) is her only gap-closer; a missed E means no engage for a while.",
        ult_note="Solar Flare stuns the center of a big area from long range; spread out after 6.",
        spike_note="Level 2 all-in with Eclipse up, and again at level 6.",
        reviewed="n", source="llm", notes="drafted",
    )  # fmt: skip
    base.update(changes)
    return base


def test_a_good_row_is_valid():
    assert validate_traits([row()], CONTEXT) == []


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"early": "4"}, "early must be 0-3"),
        ({"cc": "x"}, "cc must be 0-3"),
        ({"roam": ""}, "roam is empty"),  # drafted rows are complete
        ({"spikes": "6|2"}, "ascending"),
        ({"spikes": "6|6"}, "ascending"),
        ({"spikes": "19"}, "levels 1-18"),
        ({"tags": "airborne|tanky"}, "unknown tags tanky"),
        ({"style": "invader"}, "style must be"),
        ({"style": "ganker", "role": "support"}, "junglers only"),
        ({"role": "adc"}, "role 'adc'"),
        ({"reviewed": "y"}, "reviewed_patch"),
        ({"reviewed": "yes"}, "reviewed must be y or n"),
        ({"source": "me"}, "source must be"),
        ({"champ_id": "Nobody"}, "unknown champion"),
        ({"key_note": "x" * 241}, "longer than 240"),
        ({"key_note": "Her E hits for 75 damage."}, "numbers not in the ability text: 75"),
        ({"spike_note": "Strong once Black Cleaver is done."}, "names items (Black Cleaver)"),
        ({"ult_note": ""}, "ult_note is empty"),
    ],
)
def test_bad_values_are_reported(changes, problem):
    problems = validate_traits([row(**changes)], CONTEXT)
    assert any(problem in p for p in problems), problems


def test_allowed_numbers_and_names():
    ok = row(
        key_note="Levels 1-3 and level 6 are fine; so is 1.5 from her ability text.",
        spike_note="Eclipse is her own ability, not the item.",  # same name as an item
    )
    assert validate_traits([ok], CONTEXT) == []


def test_ability_names_containing_item_names_are_fine():
    context = TraitContext(
        champions=frozenset({"Mel"}),
        ability_names={"Mel": frozenset({"Golden Eclipse"})},
        item_names=frozenset({"Eclipse"}),
    )
    mel = {"champ_id": "Mel", "spike_note": "Stronger at level 6."}
    ok = row(**mel, ult_note="Golden Eclipse executes marked targets.")
    assert validate_traits([ok], context) == []
    bad = row(**mel, ult_note="Golden Eclipse is scary once she buys Eclipse.")
    assert any("names items (Eclipse)" in p for p in validate_traits([bad], context))


def test_prototype_rows_may_leave_new_columns_blank():
    old = row(source="prototype", roam="", waveclear="", frontline="", ult_note="", spike_note="")
    assert validate_traits([old], CONTEXT) == []
    reviewed = row(source="prototype", reviewed="y", reviewed_patch="16.19.1", roam="")
    assert any("roam is empty" in p for p in validate_traits([reviewed], CONTEXT))


def test_duplicate_rows_and_bad_columns():
    problems = validate_traits([row(), row()], CONTEXT)
    assert any("duplicate row" in p for p in problems)
    assert any("columns" in p for p in validate_traits([{"champ_id": "Leona"}], CONTEXT))


def test_checks_needing_static_data_are_skipped_without_it():
    loose = row(champ_id="Anyone", key_note="Deals 75 damage.")
    assert validate_traits([loose], TraitContext()) == []


def test_parse_and_role_lookup():
    any_role = parse_traits(row())
    assert (any_role.early, any_role.roam, any_role.spikes) == (3, 1, (2, 6))
    assert any_role.tags == {"airborne", "ult_engage"} and not any_role.reviewed
    support = parse_traits(row(role="support", early="2"))
    traits = {("Leona", ""): any_role, ("Leona", "support"): support}
    assert traits_for(traits, "Leona", Role.SUPPORT) is support
    assert traits_for(traits, "Leona", Role.TOP) is any_role
    assert traits_for(traits, "Nobody", Role.TOP) is None
    blank = parse_traits(row(source="prototype", roam=""))
    assert blank.roam is None


def test_the_committed_traits_file_is_valid(repo_paths):
    rows = read_csv(repo_paths.manual_dir / "champion_traits.csv")
    assert validate_traits(rows, TraitContext()) == []
