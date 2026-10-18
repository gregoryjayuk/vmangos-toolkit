# vmangos-toolkit

Tools and field notes for running a private vanilla World of Warcraft (1.12) server on [vMaNGOS](https://github.com/vmangos/core): an auction-house economy generator that models real item scarcity, a custom level-40 quest chain generated from the world database, persistent named party-bot companions, and a reference of every GM command in the build.

Everything here generates reviewable SQL. Nothing edits the game database by hand, and every generator deletes its own entries before inserting, so re-running is always safe.

## What's in it

| | |
|---|---|
| **[ahbot/v2](ahbot/v2/)** | The auction-house seeder. It reads the world DB's loot tables, spawn counts and crafting recipes to estimate how much of each item actually enters the world, then prices and stocks the auction house from that. Four economy profiles, from "vanilla as it shipped" to "epics everywhere". |
| **[quests/trial-of-four-winds](quests/trial-of-four-winds/)** | A generated level-40 milestone quest: given by every class trainer, touring four corners of the world for collection drops, ending in a choice of six weapons. No dungeons, enforced structurally by map id. |
| **[bots/COMPANIONS.md](bots/COMPANIONS.md)** | How to build persistent named party bots out of real accounts and characters, gear and spec them, and keep them through GM-level changes with an RBAC grant. |
| **[bots/SMARTER-BOTS.md](bots/SMARTER-BOTS.md)** | A review of vMaNGOS's party and battleground bots, a roadmap for making them better company (including LLM chat over a local model), and why a dead bot stays dead. |
| **[BUILDING.md](BUILDING.md)** | How to build new content safely: the client/server boundary, the schema's hard ceilings, gotchas already paid for, and the entry-ID ledger. |
| **[OPTIONS.md](OPTIONS.md)** | The switchboard: every setting the toolkit touches and the one line that changes it. |
| **[GM-COMMANDS.md](GM-COMMANDS.md)** | All 727 GM commands in this build, read from source and grouped by what you'd want to do, with what each privilege level means. |
| **[tools/build_local_db.py](tools/build_local_db.py)** | Turns a mysqldump of the world DB into a local SQLite file in about five seconds, so everything above can be designed offline. |

## The auction-house economy

The original seeder (v1, March 2025) is at [ahbot-config](https://github.com/gregoryjayuk/ahbot-config). v2 replaces its hand-tuned lists with a supply model built from the world DB itself:

```
$ ./ahbot/v2/ahbot_v2.py --sqlite --report
  1,675 items are created by a spell (crafted/conjured)
  8,168 items have at least one drop source
  19,807 items in item_template
  7,094 obtainable items eligible; 89 unreleased candidates

  RAREST obtainable items (should be near-unbuyable):
    Baron Charr's Sceptre                          supply=2.15e-10  rarity=1.00
    Sash of the Windreaver                         supply=2.50e-10  rarity=0.99
  MOST ABUNDANT (should flood the house):
    Linen Cloth                                    supply=9.71e+00  rarity=0.09
    Major Healing Potion                           supply=2.16e+01  rarity=0.06
```

| profile | feel | XP | epic drops | prices | BoP on the AH |
|---|---|---|---|---|---|
| authentic | Vanilla as it shipped. Scarcity is real; epics are a rumour. | x1 | x1 | x1 | no |
| generous | Authentic shape, softer edges. A weeknight server. | x3 | x3 | x0.45 | no |
| playground | Epics everywhere and cheap, BoP gear on the house, unreleased dev items unlocked. | x10 | x8 | x0.05 | yes |
| collector | Authentic prices, but the strange things surface. | x1 | x2 | x1 | no |

## Quick start

You need Python 3 and a vMaNGOS world-database dump (`mangos.sql.gz` from `mysqldump`).

```bash
./tools/build_local_db.py path/to/mangos.sql.gz mangos.sqlite   # ~5 s, once
./ahbot/v2/ahbot_v2.py --list-profiles
./ahbot/v2/ahbot_v2.py --sqlite --report                          # dry run, stats only
./ahbot/v2/ahbot_v2.py --sqlite --profile generous --out ahbot.sql
./quests/trial-of-four-winds/trial_of_four_winds.py quest.sql
```

Then import the SQL on the server and restart `mangosd` (the world DB is read at startup):

```bash
scp ahbot.sql server:
ssh server 'mysql --defaults-file=$HOME/.my.cnf mangos < ahbot.sql'
```

Credentials never appear in a command: `--mysql` mode reads `~/.my.cnf` only and refuses them as arguments, because `argv` is world-readable via `ps`.

## Layout

```
├── BUILDING.md              how to build new things
├── OPTIONS.md               every switch and its state
├── GM-COMMANDS.md           all 727 GM commands, from source
├── tools/build_local_db.py  world-DB dump -> mangos.sqlite
├── ahbot/
│   ├── ahbot.conf           the server's AHBot config
│   └── v2/                  scarcity model + four economy profiles
├── bots/
│   ├── COMPANIONS.md        persistent named party bots
│   └── SMARTER-BOTS.md      bot review and roadmap
└── quests/
    └── trial-of-four-winds/ the level-40 milestone quest
```

Generated SQL and `mangos.sqlite` are gitignored; regenerate them from your own dump.

## Licence

MIT for the code and notes in this repository. vMaNGOS and its databases are separate projects under their own licences; World of Warcraft is a trademark of Blizzard Entertainment.
