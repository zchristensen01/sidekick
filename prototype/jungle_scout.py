"""
Jungle scouting report: prototype.

Traits are hand-labeled on a 0-3 scale. They're starting guesses meant to be
tuned by playing. Kit identity (who has CC, escapes, early pressure) rarely
changes; exact numbers do, so pull those from Data Dragon (fetch_cooldowns).
"""
from dataclasses import dataclass


@dataclass
class Champ:
    name: str
    early: int          # kill pressure, levels 1-5
    engage: int         # can start a fight on their own BEFORE 6 (ult engages go in spikes/key)
    cc: int             # best hard CC before 6 (stun, root, knock-up)
    escape: int         # dashes, blinks, untargetability
    scaling: int        # late-game strength
    spikes: tuple = ()  # levels where they jump in power
    tags: frozenset = frozenset()
    key: str = ""       # the ability that matters + how to punish it
    style: str = ""     # junglers only: "ganker" or "farmer"


def C(*args, tags=(), **kw):
    return Champ(*args, tags=frozenset(tags), **kw)


# name, early, engage, cc, escape, scaling, spikes
CHAMPS = {c.name: c for c in [
    # bot
    C("Samira", 3, 1, 1, 2, 2, (2, 6), tags=("follows_cc",),
      key="W blocks projectiles, so bait it before throwing skillshots. Her R needs her style meter maxed first."),
    C("Jhin", 2, 0, 1, 0, 2, (2, 6),
      key="No dash. Easiest bot laner to gank. Stay out of range when his 4th shot is loaded."),
    C("Ashe", 1, 0, 1, 0, 2, (6,),
      key="No dash. Her R arrow is her only real engage; if it misses, punish."),
    C("Ezreal", 1, 0, 0, 3, 2, (),
      key="E (Arcane Shift) is his only escape. Gank right after he uses it."),
    C("Jinx", 1, 0, 1, 0, 3, (),
      key="No dash. Her passive gives big speed after a takedown, so don't let her reset fights. Weak early, a monster late."),
    C("Caitlyn", 2, 0, 1, 2, 2, (),
      key="E (net) is her escape. Bait it before committing."),
    C("Nautilus", 3, 3, 3, 0, 1, (2, 6), tags=("airborne",),
      key="Q (hook) is his main engage. If it misses he's exposed for its cooldown. R is a point-and-click knock-up."),
    C("Leona", 3, 3, 3, 0, 1, (2, 6),
      key="E (Zenith Blade) is her only gap-closer. Whiffed E = no engage for a while."),
    C("Thresh", 2, 3, 3, 1, 1, (2,), tags=("airborne",),
      key="Q (hook) is his engage; a miss is your window. Lantern can pull in a second engager."),
    C("Alistar", 2, 3, 3, 0, 1, (2,), tags=("airborne",),
      key="W-Q combo knocks up but he has to walk up to do it. Don't dump damage into his R."),
    C("Lulu", 1, 0, 2, 0, 2, (), tags=("peel",),
      key="W polymorph shuts down a dive. Bait it before committing."),
    # mid
    C("Yasuo", 2, 1, 2, 3, 2, (), tags=("needs_airborne", "airborne"),
      key="W (Wind Wall) blocks projectiles. His R only works on knocked-up targets."),
    C("Ahri", 2, 2, 2, 3, 2, (6,),
      key="E (charm) is her only CC; once it's down she can't catch you. R makes her hard to gank after 6."),
    C("Zed", 2, 2, 0, 3, 2, (6,),
      key="W shadow is his escape and his trade. Gank right after he uses it."),
    # top
    C("Malphite", 1, 1, 1, 0, 2, (6,), tags=("airborne",),
      key="R (Unstoppable Force) is an AoE knock-up and basically his whole teamfight. Spread out when it's up."),
    C("Cho'Gath", 1, 1, 2, 0, 3, (6,), tags=("airborne",),
      key="Q (Rupture) knock-up is slow to land. Dodge it and he has little else."),
    C("Darius", 3, 2, 1, 0, 2, (3, 6),
      key="Never fight him at 5 bleed stacks. E pull is his only gap-close; once it's down, kite."),
    C("Teemo", 2, 0, 0, 1, 2, (6,),
      key="Q blind cancels your autos for a few seconds, so trade right after he uses it. After 6, don't walk through unwarded bushes (mushrooms)."),
    C("Garen", 2, 1, 1, 1, 2, (6,),
      key="No hard CC, but Q removes slows. Gank him with hard CC, not slows."),
    # jungle
    C("Lee Sin", 3, 2, 1, 3, 1, (3, 6), tags=("airborne",), style="ganker",
      key="R kick can knock someone into his team. Strong early, falls off."),
    C("Elise", 3, 2, 2, 2, 1, (3,), style="ganker",
      key="Human E (cocoon) is her catch. If it misses, the gank usually fails."),
    C("Amumu", 2, 3, 3, 0, 2, (6,), style="ganker",
      key="Q (Bandage Toss) opens his ganks; a miss usually ends the gank."),
    C("Karthus", 0, 0, 0, 0, 3, (6,), style="farmer",
      key="Farms early. After 6 his global R can finish anyone low in any lane."),
]}

LANES = {"top": ["top"], "mid": ["mid"], "bot": ["adc", "support"]}


def lane_power(champs):
    """Early fighting power of one side of a lane."""
    return (sum(c.early for c in champs) / len(champs)
            + max(c.engage for c in champs)
            + 0.5 * max(c.cc for c in champs))


def volatility_label(v):
    return "VERY VOLATILE" if v >= 7 else "volatile" if v >= 5 else "calm"


def gank_score(targets, laners, jungler):
    """How good a gank on `targets` is for `laners` + `jungler`."""
    score = (3 - min(c.escape for c in targets)) * 1.5   # someone with no escape
    score += max(c.cc for c in laners) + 0.5 * jungler.cc
    score -= sum(1.5 for c in targets if "peel" in c.tags)
    score += 0.5 * max(0, lane_power(laners) - lane_power(targets))  # winning lanes convert
    return score


def synergies(team):
    out = []
    for a in team:
        for b in team:
            if a is b:
                continue
            if "needs_airborne" in a.tags and "airborne" in b.tags:
                out.append(f"{a.name} + {b.name}: when {b.name} knocks someone up, expect {a.name} R right after.")
            if "follows_cc" in a.tags and b.cc >= 3:
                out.append(f"{a.name} + {b.name}: whatever {b.name} locks down, {a.name} dashes onto.")
    return out


def report(ally, enemy):
    """ally/enemy: dicts of role -> champ name (top, jungle, mid, adc, support)."""
    A = {r: CHAMPS[n] for r, n in ally.items()}
    E = {r: CHAMPS[n] for r, n in enemy.items()}
    my_jg, their_jg = A["jungle"], E["jungle"]
    out = []

    out.append("== LANES ==")
    gank_rank = []
    for lane, roles in LANES.items():
        ours, theirs = [A[r] for r in roles], [E[r] for r in roles]
        pa, pe = lane_power(ours), lane_power(theirs)
        v = max(pa, pe)
        names = lambda cs: "/".join(c.name for c in cs)
        out.append(f"\n{lane.upper()}: {names(ours)} vs {names(theirs)} [{volatility_label(v)}]")

        if pe - pa >= 1.5:
            out.append("  In trouble early.")
            if lane == "bot" and max(c.engage for c in theirs) >= 3:
                out.append("  Expect a level 2 all-in. Let them push wave 1, don't race for level 2, "
                           "play near tower, ward river and ping jungle. Their overextension is your gank.")
        elif pa - pe >= 1.5:
            out.append("  Wins early. Good lane to play around.")
        else:
            out.append("  Even early. Whoever's jungler shows up first wins it.")

        for c in theirs:
            out.append(f"  {c.name}: {c.key}")
        gank_rank.append((gank_score(theirs, ours, my_jg) + (1 if v >= 5 else 0), lane))

    out.append("\n== YOUR GANKS ==")
    for i, (s, lane) in enumerate(sorted(gank_rank, reverse=True), 1):
        out.append(f"  {i}. {lane} (score {s:.1f})")

    out.append(f"\n== ENEMY JUNGLER: {their_jg.name} ({their_jg.style}) ==")
    out.append(f"  {their_jg.key}")
    if their_jg.style == "ganker":
        threat = max(LANES, key=lambda l: gank_score([A[r] for r in LANES[l]], [E[r] for r in LANES[l]], their_jg))
        out.append(f"  Most likely first gank: {threat}. Ward that side of river before your first clear ends.")
    else:
        out.append("  Wants to farm early. You can invade or force early fights.")
    if my_jg.early - their_jg.early >= 1:
        out.append("  You win early 1v1. Contest scuttle, consider invading.")
    elif their_jg.early - my_jg.early >= 1:
        out.append("  They win early 1v1. Don't fight them alone; track them instead.")

    for label, team in (("ENEMY", E.values()), ("YOUR", A.values())):
        combos = synergies(list(team))
        if combos:
            out.append(f"\n== {label} COMBOS ==")
            out += [f"  {s}" for s in combos]

    return "\n".join(out)


# ---- Optional live data (pip install requests) ----

def fetch_cooldowns(champ_id, version=None):
    """Exact per-rank cooldowns from Data Dragon. champ_id is Riot's ID, e.g. 'Nautilus', 'Chogath'."""
    import requests
    base = "https://ddragon.leagueoflegends.com"
    version = version or requests.get(f"{base}/api/versions.json").json()[0]
    data = requests.get(f"{base}/cdn/{version}/data/en_US/champion/{champ_id}.json").json()
    spells = data["data"][champ_id]["spells"]
    return {k: (s["name"], s["cooldown"]) for k, s in zip("QWER", spells)}


def likely_duos(puuids, api_key, region="americas", n=20, min_shared=3):
    """Players who keep showing up in each other's recent games are probably premade.
    Get enemy puuids from spectator-v5 once the game loads (ranked hides names in champ select)."""
    import requests
    url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{{}}/ids?count={n}"
    recent = {p: set(requests.get(url.format(p), headers={"X-Riot-Token": api_key}).json()) for p in puuids}
    ps = list(puuids)
    return [(a, b, len(recent[a] & recent[b]))
            for i, a in enumerate(ps) for b in ps[i + 1:]
            if len(recent[a] & recent[b]) >= min_shared]


if __name__ == "__main__":
    ally = {"top": "Garen", "jungle": "Lee Sin", "mid": "Ahri", "adc": "Jhin", "support": "Lulu"}
    enemy = {"top": "Malphite", "jungle": "Elise", "mid": "Yasuo", "adc": "Samira", "support": "Nautilus"}
    print(report(ally, enemy))
