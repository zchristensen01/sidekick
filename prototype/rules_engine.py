"""
Evaluates league_rules.yaml against a game and returns the rules that fired.
Feed ONLY the fired rules (plus champ facts) to the report-writing LLM.

pip install pyyaml
"""
import operator
from collections import Counter
from statistics import mean

import yaml

from jungle_scout import CHAMPS, LANES, lane_power

# Riot class + melee/ranged. Hand-filled placeholders: replace with an auto-pull
# from the LoL wiki (Module:ChampionData: "role", "rangetype") or Data Dragon
# (tags + stats.attackrange) so every champ is covered.
META = {
    "Samira": ("marksman", "ranged"), "Jhin": ("marksman", "ranged"), "Ashe": ("marksman", "ranged"),
    "Ezreal": ("marksman", "ranged"), "Caitlyn": ("marksman", "ranged"), "Jinx": ("marksman", "ranged"),
    "Nautilus": ("vanguard", "melee"), "Leona": ("vanguard", "melee"), "Alistar": ("vanguard", "melee"),
    "Thresh": ("catcher", "ranged"), "Lulu": ("enchanter", "ranged"),
    "Yasuo": ("skirmisher", "melee"), "Ahri": ("burst_mage", "ranged"), "Zed": ("assassin", "melee"),
    "Malphite": ("vanguard", "melee"), "Cho'Gath": ("specialist", "melee"), "Darius": ("juggernaut", "melee"),
    "Garen": ("juggernaut", "melee"), "Teemo": ("specialist", "ranged"),
    "Lee Sin": ("diver", "melee"), "Elise": ("burst_mage", "ranged"), "Amumu": ("vanguard", "melee"),
    "Karthus": ("battlemage", "ranged"),
}
EXTRA_TAGS = {"Karthus": {"global"}, "Malphite": {"ult_engage"}}
CLASSES = {cls for cls, _ in META.values()}

OPS = {"==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le,
       ">": operator.gt, "<": operator.lt,
       "in": lambda a, b: a in b, "has": lambda a, b: b in a}


def champ_ctx(name, role=""):
    c = CHAMPS[name]
    cls, rng = META[name]
    return dict(name=name, role=role, early=c.early, engage=c.engage, cc=c.cc, escape=c.escape,
                scaling=c.scaling, style=c.style, cls=cls, range=rng,
                tags=set(c.tags) | EXTRA_TAGS.get(name, set()))


def side_ctx(team, roles):
    champs = [champ_ctx(team[r]) for r in roles]
    carry = champs[0]  # solo laner, or the ADC in bot
    ctx = dict(
        names="/".join(c["name"] for c in champs),
        early=mean(c["early"] for c in champs), engage=max(c["engage"] for c in champs),
        cc=max(c["cc"] for c in champs), scaling=mean(c["scaling"] for c in champs),
        escape=carry["escape"], range=carry["range"],
        power=lane_power([CHAMPS[team[r]] for r in roles]),
        classes={c["cls"] for c in champs}, tags=set().union(*(c["tags"] for c in champs)),
    )
    if roles == ["adc", "support"]:
        ctx["adc"], ctx["sup"] = champs
    return ctx


def team_ctx(team):
    champs = [champ_ctx(n) for n in team.values()]
    counts = Counter(c["cls"] for c in champs)
    ctx = dict(early=mean(c["early"] for c in champs), scaling=mean(c["scaling"] for c in champs),
               n_engagers=sum(c["engage"] >= 3 or "ult_engage" in c["tags"] for c in champs))
    ctx.update({f"n_{cls}": counts.get(cls, 0) for cls in CLASSES})
    return ctx


def get(ctx, path):
    for key in path.split("."):
        ctx = ctx[key]
    return ctx


def matches(rule, ctx):
    return all(OPS[op](get(ctx, path), val) for path, op, val in rule["when"])


class _Fill(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def fire(rule, ctx, fill, out, **extra):
    if matches(rule, ctx):
        out.append(dict(id=rule["id"], confidence=rule["confidence"],
                        text=rule["say"].format_map(_Fill(fill)), **extra))


def evaluate(ally, enemy, my_role="jungle", rules_path="league_rules.yaml"):
    """ally/enemy: role -> champ name. my_role: top | jungle | mid | bot."""
    rules = yaml.safe_load(open(rules_path))["rules"]
    is_jg = my_role == "jungle"
    fired = []

    lane_diffs = {}
    for lane, roles in LANES.items():
        us, them = side_ctx(ally, roles), side_ctx(enemy, roles)
        diff = us["power"] - them["power"]
        lane_diffs[lane] = {"diff": diff}
        if not is_jg and lane != my_role:
            continue
        ctx = dict(us=us, them=them, diff=diff, volatility=max(us["power"], them["power"]),
                   range_mismatch=lane == "top" and us["range"] != them["range"])
        fill = dict(lane=lane, us=us["names"], them=them["names"])
        for r in rules:
            if r["scope"] != "lane" or lane not in r.get("lanes", LANES):
                continue
            if r.get("audience") == "jungle" and not is_jg:
                continue
            fire(r, ctx, fill, fired, lane=lane)

    if is_jg:
        us_jg, them_jg = champ_ctx(ally["jungle"]), champ_ctx(enemy["jungle"])
        ctx = dict(us=dict(jg=us_jg), them=dict(jg=them_jg), lanes=lane_diffs,
                   jg_diff=us_jg["early"] - them_jg["early"])
        fill = dict(us_jg=us_jg["name"], them_jg=them_jg["name"])
        for r in (r for r in rules if r["scope"] == "jungle"):
            fire(r, ctx, fill, fired)

    ut, tt = team_ctx(ally), team_ctx(enemy)
    ctx = dict(us=dict(team=ut), them=dict(team=tt),
               early_diff=ut["early"] - tt["early"], scaling_diff=ut["scaling"] - tt["scaling"])
    for r in (r for r in rules if r["scope"] == "team"):
        fire(r, ctx, {}, fired)

    for role, name in enemy.items():
        c = champ_ctx(name, role)
        for r in (r for r in rules if r["scope"] == "champ"):
            fire(r, dict(them=c), dict(name=name), fired)

    for label, team in (("Enemy", enemy), ("Your", ally)):
        champs = [champ_ctx(n, r) for r, n in team.items()]
        for r in (r for r in rules if r["scope"] == "pair"):
            for a in champs:
                for b in champs:
                    if a is not b:
                        fire(r, dict(a=a, b=b), dict(team=label, a=a["name"], b=b["name"]), fired)

    return fired


def as_prompt_block(fired):
    """Compact text block to paste into the LLM prompt."""
    return "\n".join(f"[{f['id']}] ({f['confidence']}) {f['text']}" for f in fired)


if __name__ == "__main__":
    ally = {"top": "Garen", "jungle": "Lee Sin", "mid": "Ahri", "adc": "Jhin", "support": "Lulu"}
    enemy = {"top": "Malphite", "jungle": "Elise", "mid": "Yasuo", "adc": "Samira", "support": "Nautilus"}
    print("=== JUNGLER VIEW ===")
    print(as_prompt_block(evaluate(ally, enemy, "jungle")))

    ally2 = {"top": "Darius", "jungle": "Amumu", "mid": "Zed", "adc": "Ezreal", "support": "Leona"}
    enemy2 = {"top": "Teemo", "jungle": "Karthus", "mid": "Ahri", "adc": "Jinx", "support": "Lulu"}
    print("\n=== TOP LANER VIEW ===")
    print(as_prompt_block(evaluate(ally2, enemy2, "top")))
