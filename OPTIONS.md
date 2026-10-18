# The switchboard — what exists, and how to turn it on or off

Everything in this toolkit, what it currently does, and the one line to change it. Written 21 Aug 2026.

> ⚠ **Re-pointed 31 Aug 2026 — the server underneath this file changed.** Greg
> retired the original core and now plays the one built 22 Aug (`~/vmangos-test`,
> commit `6958f266`). Every command here used to say
> `systemctl --user restart vmangos-mangosd.service` and
> `mysql … .my.cnf mangos <`; both now name the live units and the live
> `test_*` databases. **The settings values below were read off the OLD config on
> 21 Aug and have not been re-verified against the new one** — treat them as a
> map, not as gospel, and check `~/vmangos-test/etc/mangosd.conf` before relying
> on a number.

**Anything touching `item_template`, `quest_template` or loot needs a mangosd
restart to take effect** — the world DB is read at startup:

```bash
ssh server 'systemctl --user restart vmangos-test-mangosd.service'
```

**The auction pool does NOT need a restart to regenerate**, but AHBot only
re-seeds the live house on startup, so a restart is how you see changes.

⚠ **If an item's stats look wrong in game but right in the DB, it's the client.**
The 1.12 client caches item data in `WDB/ItemCache.wdb` and will not re-query
what it thinks it knows. Quit, delete that file, log back in. Models changing
while stats don't is the signature.

---

## 1. Auction house — `ahbot_v2.py`

### Switch the whole economy

```bash
./ahbot/v2/ahbot_v2.py --list-profiles
./ahbot/v2/ahbot_v2.py --sqlite --profile playground --out ahbot/v2/playground.sql
```

| profile | XP | epic drops | prices | BoP on AH | unreleased items |
|---|---|---|---|---|---|
| `authentic` | ×1 | ×1 | ×1 | no | 6% |
| `generous` | ×3 | ×3 | ×0.45 | no | 12% |
| `playground` | ×10 | ×8 | ×0.05 | **yes** | 100% |
| `collector` | ×1 | ×2 | ×1 | no | 85% |

Each profile also writes `<name>.mangosd.rates.conf` — paste those `Rate.*` lines
into `mangosd.conf` so XP and drop rates match the economy. Restart required.

**To apply a pool:**
```bash
scp <profile>.sql server:ahbot-v2/
ssh server 'mysql --defaults-file=$HOME/.my.cnf -e "TRUNCATE TABLE test_mangos.auctionhousebot"'
ssh server 'mysql --defaults-file=$HOME/.my.cnf test_mangos < ~/ahbot-v2/<profile>.sql'
ssh server 'systemctl --user restart vmangos-test-mangosd.service'
```
Old pool is dumped to the backup dir before any truncate. Existing live auctions
survive and age out over 48h, so the house changes over gradually.

### Force specific items into the pool

`FORCE_INCLUDE` near the top of `ahbot/v2/ahbot_v2.py`. Currently holds the 13-piece
**"90 Epic Rogue"** leather set (entries 20267–20279) — pure Agi/Str/Sta, zero
Int, zero Spirit, `allowable_class = -1` so any class wears it. A feral druid
endgame set in all but name. The Tunic is armor 257 against Dreamwalker Tunic
(real druid tier 3) at 262, so it is *not* overpowered.

`FORCE_ROWS = 1` — one pool row each, so they appear occasionally. Raise it to
make them common. These bypass eligibility filters but **not** pricing: with no
world source they price at maximum rarity, 267g–20,000g per piece.

### The two feral staves — currently OFF

| entry | item | |
|---|---|---|
| **20372** | `Test Staff 77 epic` | ilvl 77, armor 170, **+280 feral attack power** |
| **20370** | `Test Staff 90 epic` | ilvl 90, armor 240, **+574 feral attack power** |

The only staves in the game with feral AP. Blocked by `NAME_BLOCKLIST` containing
`"test"`. To enable, add the entry to `FORCE_INCLUDE` — that bypasses the name
filter. **+574 would comprehensively trivialise anything you point it at.**
Consider putting them in `playground` only.

### Other knobs

| setting | now | effect |
|---|---|---|
| `SEED` | `20260821` | changes which rumour items get picked. Same seed = same pool, always |
| `RUMOUR_SAMPLE` | per-profile | fraction of unreleased items seeded |
| `NAME_BLOCKLIST` | incl. `test` | drops dev/debug items by name |
| `TARGET_POOL_ROWS` | 22000 | total pool size |
| `price_cap_g` | 20000 (authentic) | gold ceiling per listing |
| `QUALITY_DAMP` | mats/consumables | stops a ×110 legendary multiplier landing on reagents |

---

## 2. The quest — `quests/trial-of-four-winds/trial_of_four_winds.py`

```bash
./quests/trial-of-four-winds/trial_of_four_winds.py out.sql
cp out.sql ~/quests/trial_of_four_winds.sql
ssh server 'mysql --defaults-file=$HOME/.my.cnf test_mangos < ~/quests/trial_of_four_winds.sql'
ssh server 'systemctl --user restart vmangos-test-mangosd.service'
```

The script is idempotent — it `DELETE`s its own entries before inserting, so
re-running it is always safe.

| setting | now | effect |
|---|---|---|
| `HINT_LEVEL` | `"creature"` | `creature` = names zone and mobs · `zone` = zone only · `cryptic` = neither |
| `DROP_PCT` | `30.0` | token drop chance |
| `NEED` | `8` | tokens per objective |
| `TARGET_DPS` | `47.9` | reward weapon DPS |
| `WINDS` | 4 entries | which zones and mobs. Each is `(token, name, [creature entries], zone, map, hint)` |
| `REWARDS` | 6 entries | `display` = model, `armor`, `spell`, `stats`, `speed` |

**Staff models** — `display` on the first reward, currently `24014`:

| id | |
|---|---|
| 24014 | Wildstaff *(current)* |
| 18289 | Moonshadow Stave |
| 32909 | Feral Staff |
| 20316 | Windweaver Staff |
| 35632 | Atiesh, Greatstaff of the Guardian — spectacular, arguably absurd at 40 |

**Attack power** — `AP_MELEE = 9336` (+30). The full `Attack Power NN` series runs
+2 to +100 in steps of 2; pick any and the number in the name is the value.
⚠ Feral-specific AP starts at **+140** (spell 26153) and there is nothing smaller.
New spells cannot be authored — spells live in the client's `Spell.dbc`, not the
database. That is the whole reason the staff carries generic AP.

**Quest-gating the tokens (not currently on).** Loot uses a *positive*
`ChanceOrQuestChance`, so tokens drop for anyone at any time. A **negative** value
makes them quest-only, which is correct vanilla behaviour and stops them
cluttering bags. Change `DROP_PCT = 30.0` to `-30.0`. Left positive for now
because positive is the more reliable of the two.

**Other tiers.** Only level 40 exists. For 10/20/30/50/60: change the creature
list, re-measure the DPS budget for that band, and re-run. ⚠ Tier 60 wants a
decision — 59.3 DPS sits *above* the median level-60 epic.

⚠ `RewChoiceItemId` has exactly **6 slots**, so six weapons per tier is a hard
ceiling. The 3-branch design (three claim-quests, 18 weapons) is the way past it.

---

## 3. Backups

Automatic: the server dumps at **04:32** nightly, a sync tool carries the dump to a second machine,
and a watchdog there verifies it at **06:15**.

```bash
ssh server 'bash ~/bin/vmangos-backup.sh'    # run one now
~/bin/vmangos-pull.sh                         # verify what arrived
tail -20 ~/Library/Logs/vmangos-pull.log      # what it found
```

The watchdog checks existence, freshness (>36h = the timer is dead), checksums,
non-emptiness, and that no live credential rode along.

⚠ **Configs are redacted leaving the server.** `realmd.conf` and `mangosd.conf` carry
the DB password in plaintext across five `*Database.Info` strings. The raw copies
stay on the box at mode 700; anything leaving gets `__PASSWORD_REDACTED__`. Both
ends enforce it independently. A restore needs the password typed back by hand —
that is deliberate.

**To restore:**
```bash
gzip -dc backups/characters.sql.gz | \
  ssh server 'mysql --defaults-file=$HOME/.my.cnf test_characters'
```

---

## 4. Rollback

| what | how |
|---|---|
| auction pool | `TRUNCATE test_mangos.auctionhousebot`, import the old dump from the backup dir |
| the quest | run the `DELETE` lines at the foot of `trial_of_four_winds.sql` |
| MariaDB bind | uncomment `bind-address` in `/etc/my.cnf.d/server.cnf`, restart mariadb |
| everything | restore from the nightly backup |
