# AHBot v2 — a scarcity model derived from the world itself

Same workflow as v1.4: **Python reads the DB → writes a reviewable `.sql` file →
you import that file.** Nothing ever writes to the game database directly.

## Why v2 exists

v1.4 priced every item as `sell_price × fixed multiplier × uniform(0.75, 1.25)`
and handed out 1–6 pool rows regardless of what the item was. So rare gear was
always buyable, nothing felt scarce, and price carried no information about how
hard something is to get.

v2 asks a different question: **how fast does the world actually produce this
item?**

```
supply_rate(item) = Σ over every drop source of
                      spawns × P(drop) × E[count] / respawn_seconds
```

computed from the real loot tables — 232,311 creature-loot rows against 66,083
world spawn points — resolving `reference_loot_template` recursively and
honouring MaNGOS loot-group semantics. That one number then drives **both** how
often an item appears **and** what it costs.

## The thing v1.4 got structurally wrong

`auctionhousebot` is **not a list of live auctions**. It is a *pool* AHBot draws
from at random to top the house up to its configured item count. So an item's
appearance rate is set by **how many rows it has in the pool**.

v2 allocates rows proportional to `supply × demand`. Thorium Bar floods the
house; Teebu's Blazing Longsword gets exactly one row and shows up almost never.

## Validation — the model finds the right answers unprompted

The rarest obtainable items it identifies, from first principles:

    Baron Charr's Sceptre · Sash of the Windreaver ·
    Tempestria's Frozen Necklace · Avalanchion's Stony Hide

Those are the Elemental Invasion rare-spawn drops — genuinely among the hardest
things to obtain in vanilla. Nobody told it that; it fell out of spawn counts and
respawn timers.

## Profiles — the mode system

The auction house is only half of how a server feels; XP and drop rates are the
other half. Keeping them in two hand-edited places is how they drift apart. So a
**profile** sets both: it generates the auction pool *and* writes the matching
`mangosd.conf` rate block beside it.

```bash
./ahbot_v2.py --list-profiles
./ahbot_v2.py --sqlite mangos.sqlite --profile playground --out playground.sql
# -> playground.sql  +  playground.mangosd.rates.conf
```

| profile | for | XP | epic drops | prices | BoP on AH |
|---|---|---|---|---|---|
| `authentic` | vanilla as it shipped | ×1 | ×1 | ×1 | no |
| `generous` | a weeknight server | ×3 | ×3 | ×0.45 | no |
| `playground` | mess about, kill stuff | ×10 | ×8 | ×0.05 | **yes** |
| `collector` | hunt oddities, economy intact | ×1 | ×2 | ×1 | no |

What actually changes, same items across all four:

| item | authentic | generous | playground | collector |
|---|---|---|---|---|
| Krol Blade | 3× @ 634g | 6× @ 294g | 8× @ 23g | 5× @ 677g |
| Teebu's Blazing Longsword | 1× @ 2123g | 3× @ 548g | 6× @ 66g | 2× @ 2761g |
| Thunderfury | — | — | **3× @ 400g** | — |
| Lionheart Helm | 4× @ 395g | 9× @ 181g | 11× @ 10g | 7× @ 367g |
| Linen Cloth | 12× @ ~12s | 7× | — | 9× |

Three things worth noticing:

- **`playground` puts BoP gear on the auction house.** Thunderfury and
  Quel'Serrar are *not purchasable in any other profile* — binding happens on
  purchase, so listing them is legal and it is the single biggest lever on
  "awesome gear, just play".
- **`price_cap_g`** stops that being theatre. Uncapped, Thunderfury priced at
  106,000g in playground, which is not grab-it-and-go. Capped at 400g it is.
- **`playground` drops white items** (`min_quality: 2`) so the house isn't
  cluttered with Linen Cloth when you're there to grab epics.

Profiles live in one dict at the top of `ahbot_v2.py`. Adding `twink19` or
`ironman` is a five-line edit.

⚠ The rate keys are standard MaNGOS, but **verify against your own
`~/vmangos/etc/mangosd.conf.dist` before pasting** — an unknown key is ignored
silently, so a typo looks exactly like a setting that didn't work. Needs a
`mangosd` restart.

## Running it

```bash
# Run from the PROJECT ROOT. mangos.sqlite is shared with the quest tooling and
# lives there; the scripts resolve it from their own location, not the cwd.

# one-off: build the local snapshot from any backup dump (~5 s)
./tools/build_local_db.py backups/mangos.sql.gz mangos.sqlite

# dry run — stats only, no SQL
./ahbot/v2/ahbot_v2.py --sqlite --report

# generate
./ahbot/v2/ahbot_v2.py --sqlite --out ahbot/v2/ahbot_v2_inserts.sql

# or straight against the live server
./ahbot/v2/ahbot_v2.py --mysql --out ahbot/v2/inserts.sql   # creds from ~/.my.cnf only
```

**World-DB content is static — playing does not change `item_template` or the
loot tables — so a world-DB dump is as good as a live connection for this.** That
is why none of this needs the server.

### Before importing

```bash
mysqldump mangos auctionhousebot > auctionhousebot.pre-v2.sql   # keep the old pool
```

Then `TRUNCATE mangos.auctionhousebot;` and import. AHBot re-seeds from the pool
the next time `mangosd` starts.

## Current output

| | v1.4 | v2 |
|---|---|---|
| pool rows | 21,758 | 21,840 |
| distinct items | ~5,000 | 6,505 |
| frequency model | random 1–6 | ∝ supply × demand |
| price model | uniform ±25% | log-normal, σ scales with rarity |
| unreleased items | excluded | 7 seeded as rumours |

## What's modelled

- **Supply** — creature loot, gameobject/chest loot, skinning, fishing,
  pickpocketing, item loot, vendors (infinite faucet), and **crafting**.
- **Demand** — trade goods ×3.2, consumables ×2.1, reagents ×1.6, down to
  miscellaneous ×0.55; plus bonuses for twink brackets (19/29/39/49), real stat
  allocation, and on-equip procs. Mats dominate the listings, as in a real AH.
- **Price** — `sell_price × quality × demand × scarcity_premium`, then a
  **log-normal** draw (`σ` from 0.26 for commons to 0.62 for the rarest) so you
  get a fat cheap middle and a few outrageous listings, which is how real markets
  actually distribute. Never lists below vendor price.
- **The rumours** — items obtainable from **no loot table, no vendor and no
  recipe** never shipped. That data-driven test is how the level-90 druid maces
  and cut legendaries fall out without a hand-written name list. 6% are kept, at
  8–60× price, one pool row each.

## Known tuning points

1. ⚠ **`sell_price` is a weak base for high-demand mats.** Black Lotus prices at
   ~3.7g each; on a populated vanilla realm it was 20–50g. Vendor sell price
   simply doesn't encode player demand for herbs. Fix by adding a per-subclass
   demand override (herbs, elemental mats) or raising `CLASS_DEMAND[7]`.
2. Gathering supply (skinning/fishing/herbs) is modelled as a flat contribution
   rather than from node spawns — vanilla herb/ore nodes live in client-side
   data, not the world DB, so there is nothing to count.
3. Crafted items use a quality-scaled supply floor rather than deriving scarcity
   from their reagents. Recursive reagent costing via `spell_template.reagent1-8`
   is the obvious next step and would price Arcanite properly from its inputs.
4. `SEED` at the top makes output deterministic — change it for a fresh economy.

## Files

- `build_local_db.py` — mysqldump `.sql.gz` → SQLite. Hand-rolled tuple parser
  (item names contain commas, parens and escaped quotes; a naive split silently
  corrupts the loot tables).
- `ahbot_v2.py` — the generator. All tuning knobs are in one block at the top.

## A bug found in v1.4 while reading it

`exclude_classes = [8, 10, 12, 13, 14]` is **defined and never used**. The WHERE
clause only excludes classes 12 and 13, so obsolete (8), money (10) and permanent
(14) items were being seeded into the house despite the config saying otherwise.
