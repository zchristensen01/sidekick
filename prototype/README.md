# prototype (v0)

Working reference code from the planning chat. Port the ideas into `scout/`; never import from here.

- `jungle_scout.py`: hand-labelled traits for 23 champions, lane power, gank score, synergy checks.
- `rules_engine.py`: evaluates `league_rules.yaml` against a game, prints fired rules.
- `league_rules.yaml`: about 40 generic rules (lane, top, mid, bot, jungle, team, champ, synergy).
  The live copy is `scout/rules/league_rules.yaml`; edit that one, not this.
- `AGENT_v0.md`: first draft of the writer prompt (superseded by `docs/REPORT_AGENT.md`).

Known gaps the port fixes (see `docs/ROLES.md`, `docs/DECISIONS.md`): support and ADC get no
lane rules (role vs lane mismatch), laners get no jungle information, even lanes produce no
verdict, the gank ranking isn't used by the rules, and unknown champions crash.

Run: `pip install pyyaml && python rules_engine.py`
