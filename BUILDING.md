# Building things on the vMangos server — the method

Written 22 Aug 2026, for a session picking this up cold weeks or months later.
`OPTIONS.md` is the switchboard for what already exists. **This is how to build
something new.** Read the two limits sections before designing anything.

> ⚠ **Re-pointed 31 Aug 2026.** The live server is now the core built 22 Aug
> (`~/vmangos-test`, commit `6958f266`), and its world DB is **`test_mangos`**,
> not `mangos`. The import line below used to read `.my.cnf mangos <` and the
> restart line `vmangos-mangosd.service`; a generator imported the old way now
> writes into the retired database and nothing changes in game. See
> [README.md](README.md).

---

## The loop

Everything follows the same shape, and none of it edits the game DB by hand:

```
python <generator>.py out.sql        # emit reviewable SQL
scp out.sql server:<dir>/
ssh server 'mysql --defaults-file=$HOME/.my.cnf test_mangos < ~/<dir>/out.sql'
ssh server 'systemctl --user restart vmangos-test-mangosd.service'
```

**Every generator writes `DELETE` before `INSERT` for its own entries**, so
re-running is always safe and idempotent. Do this for anything you add.

**Design offline against `mangos.sqlite`.** `tools/build_local_db.py` turns a backup
dump into a local SQLite in ~5 seconds. World-DB content is static — playing does
not change `item_template`, loot tables or creature spawns — so a dump is as good
as a live connection for design work, and you can iterate without touching the
server. Rebuild it after any schema-affecting change.

**Credentials never appear in a command.** `~/.my.cnf` on the server, mode 600.
`argv` is world-readable via `ps`.

---

## LIMIT 1 — the client/server boundary

**This is the single most important thing to internalise.** The database can only
reference what the 1.12 client already knows. Anything in a `.DBC` or `.MPQ` on
the player's machine cannot be created server-side, only pointed at.

| you want | possible? | why |
|---|---|---|
| New item with any stats, damage, procs | **yes** | `item_template` is pure DB |
| New creature, any level/rank/loot/AI | **yes** | `creature_template` + `creature` + EventAI |
| New quest, chains, choice rewards | **yes** | `quest_template` is pure DB |
| New vendor, trainer, gameobject | **yes** | pure DB |
| Change any drop rate or spawn | **yes** | pure DB |
| **New spell or spell effect** | **NO** | `Spell.dbc` is client-side |
| **New item/creature model** | **NO** | `ItemDisplayInfo.dbc`, `CreatureDisplayInfo.dbc` |
| **New terrain, zone, dungeon** | **NO** | map geometry lives in client MPQs |

Consequences that have already bitten:

- **You cannot summon anything from an item.** Needs `SPELL_EFFECT_SUMMON`. The
  Four Winds guardian stands at his cairn permanently and the talisman "makes him
  answer" narratively instead.
- **You cannot scale a spell's magnitude.** `Attack Power - Feral` starts at +140
  (spell 26153, ilvl 70) and there is nothing smaller. A level-40 item therefore
  uses generic `Attack Power 30` (spell 9336), which in vanilla applies in Cat and
  Bear form identically anyway.
- **Appearance comes from a menu, not a canvas.** Pick a `display_id` from an
  existing item of the same subclass — always query, never reuse one value across
  several items (the first cut of the Four Winds rewards had one sword model on
  all six and every reward looked identical).
- **New places are possible without new terrain.** 1.12 ships real, walkable,
  empty geometry: Hyjal, Old Ironforge, Alcaz Island, the Karazhan Crypts, GM
  Island, unfinished Uldum. Populate one with creatures and gameobjects and you
  have a custom area with zero client modding.

---

## LIMIT 2 — hard schema ceilings

Design around these; they cannot be raised.

| field | limit | consequence |
|---|---|---|
| `ReqItemId1..4` | **4** | four collection objectives per quest |
| `ReqCreatureOrGOId1..4` | **4** | four kill/use objectives per quest |
| `RewChoiceItemId1..6` | **6** | six choice rewards per quest |
| `RewItemId1..4` | 4 | four guaranteed rewards |
| `stat_type1..10` | 10 | ten stats per item |
| `spellid_1..5` | 5 | five spell effects per item |

**The 6-slot reward ceiling is the binding one.** Vanilla has ~15 weapon types.
To offer more than six, end a chain in *several parallel claim-quests* — group by
weapon family, link them with a **negative `ExclusiveGroup`** so completing one
locks the others. Three branches × 6 = 18 without touching the ceiling.

---

## Gotchas already paid for

Each of these cost real debugging. None are guessable.

1. **`creature_template` has one row per content PATCH.** `SELECT entry` returns
   duplicates. A questgiver insert died on the `(id,quest)` primary key at 211 of
   257 trainers — leaving a *half-populated* relation table, far worse than an
   outright failure. **Always `SELECT DISTINCT entry`.**

2. **`ZoneOrSort = 0` renders as "missing header"** in the quest log. It is not a
   valid category. Use a zone id, or a negative QuestSort — **`-1` is Epic**, used
   by only two quests in the entire game.

3. **The client caches item and quest data** in `WDB/ItemCache.wdb` next to
   `WoW.exe` and will not re-query what it thinks it knows. If the DB is right and
   the tooltip is wrong, delete that file and relog. *Models updating while stats
   do not* is the signature of a partial refresh.

4. **Loot chance sign matters.** Positive `ChanceOrQuestChance` drops for anyone
   at any time. **Negative makes it quest-only**, which is correct vanilla
   behaviour for quest tokens and stops them cluttering bags.

5. **`mincountOrRef` negative means a reference** into `reference_loot_template`,
   not a count. Any supply or drop-rate analysis must resolve these **recursively**
   or it badly understates real drop chances.

6. **Overworld means `map IN (0,1)`.** Eastern Kingdoms and Kalimdor. Instances
   have their own map ids, so filtering on these two is a *structural* guarantee of
   "no dungeons" rather than relying on memory of which mob lives where.

7. **Balance content by total spawn points, not by counting mob types.** The
   Hinterlands leg of the Four Winds had one source with 32 spawns against
   Feralas's 264 — eight times grindier, and it reads to the player as
   respawn-camping rather than a hunt.

8. **`mysqldump` needs `--lock-tables`, never `--single-transaction`.** 88% of
   `mangos` is MyISAM, which `--single-transaction` cannot dump consistently and
   **fails silently on**. You find out at restore.

---

## Measure, never guess

The world DB already contains the answer to almost any balance question. Every
number in the Four Winds quest was derived, and the derivations caught things
memory would not have:

- **Weapon DPS budget** — `(dmg_min1+dmg_max1)/2 / (delay/1000)`, taken as the
  85th percentile of BLUE items in the tier, +10%. This revealed that the *median*
  real level-40 epic is 36.9 DPS, i.e. **below a good blue** — so a 47.9 DPS epic
  beats everything genuinely obtainable without trivialising anything.
- **Feral stat budget** — best `Str+Agi+Sta` on weapons at ilvl 40-55 is 41
  (Stoneraven). The reward sits at 50: an epic's worth above, no more.
- **Armor budget** — `Warden Staff` is the same ilvl 48 and quality 4 and carries
  260. That single lookup answered "should a staff have armor" definitively.
- **Item rarity** — `supply = spawns × P(drop) × E[count] / respawn`, over the
  real loot tables. Validated by the fact that the rarest items it identified,
  unprompted, were the Elemental Invasion rare-spawn drops.
- **Landmarks** — bearings for quest text came from `game_tele` coordinates, so
  every place name genuinely exists where the text claims.

Useful sources: `item_template` (budgets, display ids), `creature_template` +
`creature` (levels, spawn density), `creature_loot_template` (drop rates),
`game_tele` (place names and coordinates), `spell_template` (what effects exist
and their magnitudes).

---

## Entry ID ledger

Custom content lives at **61000+** to stay clear of anything upstream. Check
before claiming a range:

```sql
SELECT COUNT(*) FROM item_template      WHERE entry BETWEEN 61000 AND 61999;
SELECT COUNT(*) FROM quest_template     WHERE entry BETWEEN 61000 AND 61999;
SELECT COUNT(*) FROM creature_template  WHERE entry BETWEEN 61000 AND 61999;
```

| range | used by |
|---|---|
| 61001–61002 | quests: The Trial of the Four Winds, The Fifth Wind |
| 61010–61013 | the four wind tokens |
| 61020–61021 | Wind-Bound Talisman, Heart of the Storm |
| 61100–61105 | the six reward weapons |
| 61200 | Skarn, the Fifth Wind (creature) |
| **61300+** | **free** — suggested next: gameobjects |
| **61400+** | **free** — suggested next: the level-50 tier |

---

## Recipes

**A new quest.** Copy `quests/trial-of-four-winds/trial_of_four_winds.py`. Set `ZoneOrSort` to a zone id or
`-1`. Attach to questgivers with `creature_questrelation` (gives) and
`creature_involvedrelation` (turns in) — `SELECT DISTINCT`. Class trainers are
`npc_flags & 16 AND trainer_type = 0`, which is 261 creatures and the reason the
quest can be picked up anywhere. Chain with `PrevQuestId` / `NextQuestId`; gate a
follow-on with `SrcItemId`.

**A new item.** Query a real item of the same class/subclass for `display_id`,
`inventory_type` and a stat budget. On-equip effects need `spelltrigger_N = 1`,
and `spellcharges = 0, spellcooldown = -1, spellcategory = 0,
spellcategorycooldown = -1` — copy the shape from a known-good item and diff it.

**A new creature.** Copy `level_min/max`, `faction`, `rank`, `unit_class`,
`health_multiplier`, `damage_multiplier` from an existing creature of the intended
difficulty (`Foulbelly`, entry 2601, is a solid level-42 rare elite). Then a
`creature` row for the spawn, and `creature_loot_template` for drops. Scripted
behaviour goes in `creature_ai_scripts` (EventAI) — no recompile needed.

**A new area.** Pick one of the empty vanilla zones above, then populate with
`creature` spawns and `gameobject` placements. Get coordinates from `game_tele`
or from existing spawns nearby.

---

## Before you finish

- Run the generator twice — it must be idempotent.
- Validate column names against the live schema before importing; a typo in an
  `INSERT` column list is the most common failure.
- Restart mangosd and **read the journal** for errors mentioning your entries:
  `journalctl --user -u vmangos-test-mangosd.service --since "2 minutes ago"`.
  (`DungeonReset` errors for maps 249/309/409/469/509/531/533 are pre-existing
  raid-instance noise and unrelated to anything you did.)
- Update `OPTIONS.md` with any new switch, and this file's ledger with any new
  entry range.
