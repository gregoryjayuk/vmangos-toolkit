#!/usr/bin/env python3
"""
ahbot_v2.py -- vMangos auction-house seeder with a scarcity model derived from
the world itself.

v1.4 priced everything as sell_price x fixed multiplier x uniform(0.75,1.25) and
gave every eligible item 1-6 pool rows regardless of what it was. Consequences:
rare gear was always on the AH, nothing felt scarce, and price carried no
information about how hard an item is to get.

v2 computes, for every item, how fast the WORLD ACTUALLY PRODUCES IT:

    supply_rate(item) = SUM over every drop source of
                          spawns x P(drop) x E[count] / respawn_seconds

...reading the real loot tables (232k creature-loot rows against 66k world spawn
points), resolving reference_loot_template recursively, and honouring MaNGOS
group semantics. That single number then drives BOTH how often an item appears
and what it costs.

HOW FREQUENCY ACTUALLY WORKS (this is the bit v1.4 got structurally wrong):
`auctionhousebot` is not a list of live auctions. It is a POOL that AHBot draws
from at random to top the house up to its configured item count. So an item's
appearance rate is set by HOW MANY ROWS IT HAS IN THE POOL. v2 allocates rows
proportional to supply x demand, so a Thorium Bar floods the AH and a Teebu's
Blazing Longsword shows up once in a blue moon.

Usage:
    ./ahbot_v2.py --sqlite --out ahbot_v2_inserts.sql        # root mangos.sqlite
    ./ahbot_v2.py --mysql --out inserts.sql      # creds from ~/.my.cnf ONLY
    ./ahbot_v2.py --sqlite --report                          # dry run, no SQL

Nothing is written to the game database. Output is SQL for manual review and
import, exactly like v1.4.
"""
import argparse, math, random, sqlite3, sys, os
from collections import defaultdict

# mangos.sqlite lives at the project root and is shared with the quest tooling,
# so resolve it from THIS FILE's location rather than the working directory --
# otherwise the script only works when run from one folder.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB = os.path.join(ROOT, "mangos.sqlite")

# ============================================================================
# TUNING -- every knob that shapes the economy lives here
# ============================================================================

SEED = 20260821                 # deterministic output; change for a new economy

# --- what is allowed on the auction house at all -------------------------
ALLOWED_QUALITIES  = [1, 2, 3, 4, 5]      # white .. legendary (0=grey is trash)
EXCLUDED_CLASSES   = [8, 10, 12, 13, 14]  # obsolete, money, quest, key, permanent
ALLOWED_BONDING    = (0, 2, 3)            # none / BoE / BoU -- never BoP
NAME_BLOCKLIST     = ("deprecated", "unused", "[ph]", "[unused]", "monster -",
                      "test", "(test", "qa ", "debug", "olddo not use", "do not use")

# --- pool size ------------------------------------------------------------
TARGET_POOL_ROWS   = 22000      # v1.4 produced 21,758; stay in the same ballpark
MIN_ROWS, MAX_ROWS = 1, 40      # per-item pool row bounds

# --- demand ---------------------------------------------------------------
CLASS_DEMAND = {
    7: 3.20,   # Trade Goods -- mats are the lifeblood of a real AH
    0: 2.10,   # Consumable
    5: 1.60,   # Reagent
    6: 1.40,   # Projectile
    9: 1.25,   # Recipe
    2: 1.00,   # Weapon
    4: 1.00,   # Armor
    1: 0.85,   # Container
    11: 0.70,  # Quiver
    3: 0.90,   # Gem
    15: 0.55,  # Miscellaneous
}
TWINK_LEVELS       = {19, 29, 39, 49}
TWINK_BONUS        = 1.65
GOOD_STAT_BONUS    = 1.30       # meaningful stat allocation
EQUIP_PROC_BONUS   = 1.25       # on-equip spell effect

# --- price ----------------------------------------------------------------
QUALITY_VALUE = {1: 1.20, 2: 2.60, 3: 6.50, 4: 22.0, 5: 110.0}
# Quality means different things by item class. On a weapon, "legendary" is a
# power statement and the big multiplier is right. On a REAGENT it just flags a
# rare mat -- Elementium Bar is quality 5 but it is an ingredient, and x110 sent
# a stack to 157,000g. Damp the quality curve toward 1.0 for mats and consumables.
QUALITY_DAMP = {7: 0.22, 5: 0.25, 0: 0.35, 6: 0.35}   # trade goods, reagent, consumable, projectile
SCARCITY_ALPHA = 0.34           # how hard rarity pushes price
SCARCITY_CAP   = 70.0           # ceiling on the scarcity premium
SIGMA_BASE     = 0.26           # log-normal spread, common items
SIGMA_RARE     = 0.62           # log-normal spread, rarest items
BID_FRACTION   = (0.35, 0.92)   # bid as a fraction of buyout
COPPER_CAP     = 2_000_000_000  # int(11) unsigned guard

# --- the unreleased/dev items -------------------------------------------
# Detected from DATA, not a name list: an item obtainable from no loot table
# and no vendor did not ship. That is exactly how the level-90 druid maces,
# the dev-test epics and the cut legendaries fall out.
RUMOUR_ENABLED     = True
RUMOUR_MIN_QUALITY = 3          # rare and above only
RUMOUR_SAMPLE      = 0.06       # keep 6% of them -- rumours, not a catalogue
RUMOUR_PRICE_MULT  = (8.0, 60.0)
RUMOUR_MAX_ROWS    = 1

CRAFT_SUPPLY_FLOOR = 0.30       # crafted goods are reliably available

# --- forced inclusions -----------------------------------------------------
# v1.4 had an `include_items` list and v2 dropped it -- my omission. Some items
# are worth having in the house regardless of what the scarcity model concludes.
#
# The "90 Epic Rogue" leather set (Greg, 21 Aug): 13 pieces, every one of them
# pure Agility/Strength/Stamina with zero Intellect and zero Spirit, and
# allowable_class = -1, so despite the name it is wearable by any class. For a
# feral druid it is a complete endgame set. It is NOT overpowered: the Tunic is
# armor 257 against Dreamwalker Tunic (real druid tier 3) at 262 -- a hair under.
# It has no loot source, no vendor and no recipe, so the scarcity model rates it
# maximum rarity and prices it accordingly. FORCE_ROWS 1 keeps it occasional:
# one row in a ~22,000-row pool means it surfaces now and then, not on demand.
FORCE_INCLUDE = [
    20267, 20268, 20269, 20270, 20271, 20272, 20273,   # Belt Boots Bracers Cap Gloves Pants Spaulders
    20274, 20275, 20276, 20277, 20278, 20279,          # Tunic Neck Cloak Ring Bow Dagger
]
FORCE_ROWS = 1          # pool rows each -- raise for more frequent appearances

# --- stacks ---------------------------------------------------------------
STACKABLE_CLASSES  = (0, 5, 6, 7)
FULL_STACK_CHANCE  = 0.62       # v1.4 used 0.80 -- real AHs carry more partials


# ============================================================================
# PROFILES -- named economy modes.
#
# Greg, 21 Aug: "sometimes I wanna play a character properly as if I was playing
# real WoW. But then sometimes I just wanna mess around... awesome gear and just
# play and just kill stuff."
#
# A profile reshapes the auction house AND emits a matching mangosd.conf rate
# block, so switching the feel of the whole server is one command rather than a
# pile of hand-edits that drift out of sync with each other.
# ============================================================================

PROFILES = {
    "authentic": dict(
        blurb        = "Vanilla as it shipped. Scarcity is real; epics are a rumour.",
        price_cap_g  = 20000,  # above any realistic vanilla price, below absurd
        rarity_power = 1.50,   # how hard supply drives pool rows (0 = flat)
        price_scale  = 1.00,
        sigma_scale  = 1.00,   # price spread
        quality_bias = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0},
        min_quality  = 1,
        allow_bop    = False,
        rumour_sample= 0.06,
        rates = dict(xp=1.0, quest_xp=1.0, explore_xp=1.0, money=1.0,
                     rep=1.0, honor=1.0, rest=1.0,
                     drop=dict(poor=1.0, normal=1.0, uncommon=1.0,
                               rare=1.0, epic=1.0, legendary=1.0)),
    ),
    "generous": dict(
        blurb        = "Authentic shape, softer edges. Blues are affordable, "
                       "levelling is brisk. A weeknight server.",
        rarity_power = 0.85,
        price_scale  = 0.45,
        sigma_scale  = 0.80,
        quality_bias = {1: 0.7, 2: 1.1, 3: 1.8, 4: 2.2, 5: 1.5},
        min_quality  = 1,
        allow_bop    = False,
        rumour_sample= 0.12,
        price_cap_g  = 3000,
        rates = dict(xp=3.0, quest_xp=3.0, explore_xp=3.0, money=2.0,
                     rep=2.0, honor=2.0, rest=2.0,
                     drop=dict(poor=1.0, normal=1.5, uncommon=2.0,
                               rare=2.5, epic=3.0, legendary=2.0)),
    ),
    "playground": dict(
        blurb        = "Mess about. Epics everywhere and cheap, BoP gear on the "
                       "house, the unreleased dev items unlocked. Just kill stuff.",
        rarity_power = 0.10,   # supply barely matters -- almost flat
        price_scale  = 0.05,
        sigma_scale  = 0.50,
        quality_bias = {1: 0.15, 2: 0.5, 3: 3.0, 4: 6.0, 5: 4.0},
        min_quality  = 2,      # no white trash cluttering the house
        allow_bop    = True,   # <- the big one: BoP epics become buyable
        rumour_sample= 1.00,   # every level-90 druid mace, all of them
        price_cap_g  = 400,    # grab-it-and-go: nothing costs a raid tier
        rates = dict(xp=10.0, quest_xp=10.0, explore_xp=10.0, money=5.0,
                     rep=5.0, honor=5.0, rest=5.0,
                     drop=dict(poor=1.0, normal=2.0, uncommon=4.0,
                               rare=6.0, epic=8.0, legendary=5.0)),
    ),
    "collector": dict(
        blurb        = "Authentic prices, but the strange things surface. For "
                       "hunting oddities and cut content without breaking the economy.",
        rarity_power = 1.30,
        price_scale  = 1.00,
        sigma_scale  = 1.20,
        quality_bias = {1: 0.8, 2: 1.0, 3: 1.3, 4: 1.6, 5: 2.0},
        min_quality  = 1,
        allow_bop    = False,
        rumour_sample= 0.85,
        price_cap_g  = 30000,
        rates = dict(xp=1.0, quest_xp=1.0, explore_xp=1.0, money=1.0,
                     rep=1.0, honor=1.0, rest=1.0,
                     drop=dict(poor=1.0, normal=1.0, uncommon=1.0,
                               rare=1.5, epic=2.0, legendary=3.0)),
    ),
}

P = PROFILES["authentic"]      # replaced at startup by --profile


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Loot resolution
# ---------------------------------------------------------------------------

def group_probabilities(rows):
    """MaNGOS loot-group semantics -> P(this row fires) for one source entry.

    rows: list of (item, chance, groupid, mincountOrRef, maxcount)

    groupid 0  -> independent roll at chance%.
    groupid >0 -> the group rolls once and picks at most one member. Explicit
                  chances are relative; rows with chance 0 share whatever is
                  left of 100. If the explicit chances oversubscribe 100 they
                  are normalised.
    """
    out = []
    groups = defaultdict(list)
    for r in rows:
        if r[2] == 0:
            chance = abs(r[1])
            out.append((r, min(chance, 100.0) / 100.0))
        else:
            groups[r[2]].append(r)

    for _gid, members in groups.items():
        explicit = sum(abs(m[1]) for m in members if m[1] != 0)
        zeros    = [m for m in members if m[1] == 0]
        share    = (100.0 - explicit) / len(zeros) if zeros and explicit < 100 else 0.0
        total    = max(explicit, 100.0) if explicit > 100 else 100.0
        for m in members:
            c = abs(m[1]) if m[1] != 0 else share
            out.append((m, max(0.0, c) / total))
    return out


def expand(rows, refs, depth=0, seen=None):
    """Flatten one loot list into [(item, probability, expected_count)],
    following mincountOrRef < 0 into reference_loot_template.

    Cycle-guarded and depth-capped: a malformed reference chain in a
    community world DB must not hang the generator.
    """
    if depth > 6:
        return []
    seen = seen or frozenset()
    flat = []
    for (item, _chance, _gid, mincount, maxcount), p in group_probabilities(rows):
        if p <= 0:
            continue
        if mincount < 0:                      # -> reference table
            ref = -mincount
            if ref in seen:
                continue
            sub = refs.get(ref)
            if not sub:
                continue
            times = max(1, maxcount)          # reference rolled `maxcount` times
            for it, sp, sc in expand(sub, refs, depth + 1, seen | {ref}):
                flat.append((it, p * sp, sc * times))
        else:
            lo = max(1, mincount)
            hi = max(lo, maxcount)
            flat.append((item, p, (lo + hi) / 2.0))
    return flat


# ---------------------------------------------------------------------------
# Supply
# ---------------------------------------------------------------------------

def build_supply(cx):
    """items/second the world produces, per item entry."""
    q = lambda s, *a: cx.execute(s, a).fetchall()

    log("  reading reference_loot_template ...")
    refs = defaultdict(list)
    for e, i, c, g, mn, mx in q(
            "SELECT entry,item,ChanceOrQuestChance,groupid,mincountOrRef,maxcount "
            "FROM reference_loot_template"):
        refs[e].append((i, c, g, mn, mx))

    # spawn counts: one world spawn point can roll up to five templates (id..id5)
    log("  counting creature spawns ...")
    spawns, respawn = defaultdict(float), defaultdict(list)
    for cid, i2, i3, i4, i5, smin, smax in q(
            "SELECT id,id2,id3,id4,id5,spawntimesecsmin,spawntimesecsmax FROM creature"):
        ids = [x for x in (cid, i2, i3, i4, i5) if x]
        if not ids:
            continue
        w = 1.0 / len(ids)
        rs = max(1.0, ((smin or 0) + (smax or 0)) / 2.0 or 120.0)
        for x in ids:
            spawns[x] += w
            respawn[x].append(rs)

    log("  counting gameobject spawns ...")
    go_spawns, go_respawn = defaultdict(float), defaultdict(list)
    for gid, smin, smax in q("SELECT id,spawntimesecsmin,spawntimesecsmax FROM gameobject"):
        go_spawns[gid] += 1.0
        go_respawn[gid].append(max(1.0, ((smin or 0) + (smax or 0)) / 2.0 or 300.0))

    # chests: gameobject_template.type 3 stores its loot id in data1
    go_loot = {}
    try:
        for e, t, d1 in q("SELECT entry,type,data1 FROM gameobject_template"):
            if t == 3 and d1:
                go_loot.setdefault(d1, []).append(e)
    except sqlite3.OperationalError:
        pass

    supply = defaultdict(float)

    def absorb(table, spawn_map, respawn_map, entry_to_sources=None, default_period=None):
        by_entry = defaultdict(list)
        for e, i, c, g, mn, mx in q(
                f"SELECT entry,item,ChanceOrQuestChance,groupid,mincountOrRef,maxcount FROM {table}"):
            by_entry[e].append((i, c, g, mn, mx))
        for entry, rows in by_entry.items():
            sources = entry_to_sources.get(entry, [entry]) if entry_to_sources else [entry]
            n = sum(spawn_map.get(s, 0.0) for s in sources)
            if n <= 0:
                continue
            periods = [p for s in sources for p in respawn_map.get(s, [])]
            period = (sum(periods) / len(periods)) if periods else (default_period or 300.0)
            for item, p, cnt in expand(rows, refs):
                supply[item] += n * p * cnt / period

    log("  resolving creature loot (232k rows, recursive refs) ...")
    absorb("creature_loot_template", spawns, respawn, default_period=120.0)
    log("  resolving gameobject loot ...")
    absorb("gameobject_loot_template", go_spawns, go_respawn, go_loot, default_period=300.0)

    # Gathering and pickpocketing scale with player activity, not spawn timers.
    # Model them as a flat, generous contribution -- these are abundant by nature.
    log("  folding in skinning / fishing / pickpocketing / item loot ...")
    for table, weight in (("skinning_loot_template", 0.020),
                          ("fishing_loot_template", 0.020),
                          ("pickpocketing_loot_template", 0.008),
                          ("item_loot_template", 0.010)):
        by_entry = defaultdict(list)
        for e, i, c, g, mn, mx in q(
                f"SELECT entry,item,ChanceOrQuestChance,groupid,mincountOrRef,maxcount FROM {table}"):
            by_entry[e].append((i, c, g, mn, mx))
        for _entry, rows in by_entry.items():
            for item, p, cnt in expand(rows, refs):
                supply[item] += weight * p * cnt

    vendor = set(r[0] for r in q("SELECT DISTINCT item FROM npc_vendor"))

    # Craftable / conjured items have NO loot source but are absolutely real and
    # heavily traded -- Thorium Bar, Arcanite Bar, every crafted BoE. Without this
    # they get mistaken for unreleased dev items and dropped from the pool
    # entirely. SPELL_EFFECT_CREATE_ITEM = 24; the product is in effectItemTypeN.
    craft = set()
    try:
        for e1, e2, e3, i1, i2, i3 in q(
                "SELECT effect1,effect2,effect3,effectItemType1,effectItemType2,"
                "effectItemType3 FROM spell_template"):
            for eff, item in ((e1, i1), (e2, i2), (e3, i3)):
                if eff == 24 and item:
                    craft.add(item)
    except sqlite3.OperationalError:
        log("  ! spell_template missing -- crafted items will look unobtainable")
    log(f"  {len(craft):,} items are created by a spell (crafted/conjured)")
    return supply, vendor, craft


# ---------------------------------------------------------------------------
# Demand
# ---------------------------------------------------------------------------

def demand_of(it):
    d = CLASS_DEMAND.get(it["class"], 0.8)
    if it["quality"] >= 2:
        if it["required_level"] in TWINK_LEVELS:
            d *= TWINK_BONUS
        best = max((it.get(f"stat_value{n}") or 0) for n in range(1, 11))
        if best >= 8:
            d *= GOOD_STAT_BONUS
        if it.get("spellid_1") and it.get("spelltrigger_1") == 1:
            d *= EQUIP_PROC_BONUS
    return d


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def eligible(it):
    if it["quality"] not in ALLOWED_QUALITIES:      return False
    if it["quality"] < P["min_quality"]:            return False
    if it["class"] in EXCLUDED_CLASSES:             return False
    allowed_bond = ALLOWED_BONDING + ((1,) if P["allow_bop"] else ())
    if it["bonding"] not in allowed_bond:           return False
    if (it["required_honor_rank"] or 0) != 0:       return False
    if (it["required_reputation_faction"] or 0) != 0 or (it["required_reputation_rank"] or 0) != 0:
        return False
    nm = (it["name"] or "").lower()
    if not nm or any(b in nm for b in NAME_BLOCKLIST): return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", nargs="?", const=DEFAULT_DB, default=None,
                    help=f"path to the local snapshot (default: {DEFAULT_DB})")
    ap.add_argument("--mysql", action="store_true",
                    help="read the live DB using ~/.my.cnf (chmod 600). Credentials are "
                         "NEVER accepted on the command line: argv is visible to every "
                         "user on the box via ps(1).")
    ap.add_argument("--mysql-db", default="mangos")
    ap.add_argument("--out", default="ahbot_v2_inserts.sql")
    ap.add_argument("--report", action="store_true", help="dry run -- stats only")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--profile", default="authentic", choices=sorted(PROFILES),
                    help="economy mode -- reshapes the house AND the server rates")
    ap.add_argument("--list-profiles", action="store_true")
    a = ap.parse_args()

    if a.list_profiles:
        for name, pr in PROFILES.items():
            print(f"\n  {name}\n    {pr['blurb']}")
            print(f"    XP x{pr['rates']['xp']:g} · epic drops x{pr['rates']['drop']['epic']:g}"
                  f" · prices x{pr['price_scale']:g}"
                  f" · BoP on the AH: {'yes' if pr['allow_bop'] else 'no'}")
        print()
        return

    global P
    P = PROFILES[a.profile]
    log(f"profile: {a.profile} -- {P['blurb']}")

    rng = random.Random(a.seed)

    if a.sqlite:
        cx = sqlite3.connect(os.path.expanduser(a.sqlite))
        cx.row_factory = sqlite3.Row
    elif a.mysql:
        import mysql.connector
        mycnf = os.path.expanduser("~/.my.cnf")
        if not os.path.exists(mycnf):
            sys.exit("~/.my.cnf not found. Create it (chmod 600) with:\n"
                     "  [client]\n  user=mangos\n  password=\"...\"\n"
                     "Credentials are deliberately not accepted as arguments.")
        cx = mysql.connector.connect(option_files=mycnf, database=a.mysql_db)
    else:
        sys.exit("need --sqlite or --mysql")

    log("Building supply model from the world DB ...")
    supply, vendor, craft = build_supply(cx)
    log(f"  {len(supply):,} items have at least one drop source")

    cols = ("entry,class,subclass,name,quality,item_level,required_level,sell_price,buy_price,"
            "bonding,stackable,required_honor_rank,required_reputation_faction,"
            "required_reputation_rank,spellid_1,spelltrigger_1," +
            ",".join(f"stat_value{n}" for n in range(1, 11)))
    items = [dict(r) for r in cx.execute(f"SELECT {cols} FROM item_template").fetchall()]
    log(f"  {len(items):,} items in item_template")

    live, rumours = [], []
    for it in items:
        if not eligible(it):
            continue
        e = it["entry"]
        s = supply.get(e, 0.0)
        if s <= 0 and e not in vendor and e not in craft:
            # no drop, no vendor, no recipe -> this item never shipped
            if RUMOUR_ENABLED and it["quality"] >= RUMOUR_MIN_QUALITY:
                rumours.append(it)
            continue
        if e in vendor:
            s = max(s, 0.05)              # vendors are an unlimited faucet
        if e in craft:
            # Producible on demand, but gated by reagents -- scarcer the better
            # the item. Scale the floor down as quality climbs.
            s = max(s, CRAFT_SUPPLY_FLOOR / (1.0 + 3.0 * max(0, it["quality"] - 1)))
        live.append((it, s))

    log(f"  {len(live):,} obtainable items eligible; {len(rumours):,} unreleased candidates")

    # --- normalise scarcity onto 0..1 (0 = floods the world, 1 = vanishingly rare)
    rates = sorted(s for _, s in live)
    lo, hi = math.log10(rates[0] + 1e-12), math.log10(rates[-1] + 1e-12)
    span = (hi - lo) or 1.0
    def rarity(s):
        return 1.0 - (math.log10(s + 1e-12) - lo) / span

    # --- allocate pool rows proportional to supply x demand ------------------
    weights = []
    for it, s in live:
        w = ((1.0 - rarity(s)) ** P["rarity_power"] * demand_of(it)
             * P["quality_bias"].get(it["quality"], 1.0))
        weights.append(max(w, 1e-4))
    scale = TARGET_POOL_ROWS / sum(weights)

    out, stats = [], defaultdict(int)
    for (it, s), w in zip(live, weights):
        n = max(MIN_ROWS, min(MAX_ROWS, int(round(w * scale))))
        r = rarity(s)
        for _ in range(n):
            out.append(listing(it, r, rng))
        stats["rows"] += n
        stats["items"] += 1

    # --- forced inclusions ---------------------------------------------------
    # These bypass eligibility entirely (the set is BoP-flagged in places and
    # would otherwise be filtered), but NOT the pricing model -- they are priced
    # at maximum rarity like anything else with no source in the world.
    if FORCE_INCLUDE:
        by_entry = {it["entry"]: it for it in items}
        forced = 0
        for ent in FORCE_INCLUDE:
            it = by_entry.get(ent)
            if not it:
                log(f"  ! FORCE_INCLUDE {ent} not found in item_template")
                continue
            for _ in range(FORCE_ROWS):
                out.append(listing(it, 1.0, rng))
            forced += FORCE_ROWS
        stats["forced_rows"] = forced
        stats["forced_items"] = len([e for e in FORCE_INCLUDE if e in by_entry])
        log(f"  force-included {stats['forced_items']} items, {forced} pool rows")

    # --- the rumours ---------------------------------------------------------
    rng.shuffle(rumours)
    for it in rumours[:int(round(len(rumours) * P["rumour_sample"]))]:
        for _ in range(RUMOUR_MAX_ROWS):
            out.append(listing(it, 1.0, rng, rumour=True))
        stats["rumour_rows"] += RUMOUR_MAX_ROWS
        stats["rumour_items"] += 1

    report(live, rumours, stats, supply, rarity)
    if a.report:
        log("\n(dry run -- no SQL written)")
        return

    rng.shuffle(out)
    with open(os.path.expanduser(a.out), "w") as f:
        f.write("-- ahbot_v2 -- generated seed pool for vMangos AuctionHouseBot\n")
        f.write(f"-- seed={a.seed}  rows={len(out):,}\n")
        f.write("-- Review before importing. Suggested: TRUNCATE first, or keep a copy of the\n")
        f.write("-- old pool -- `mysqldump mangos auctionhousebot > auctionhousebot.pre-v2.sql`\n\n")
        for entry, stack, bid, buyout, name in out:
            f.write(f"INSERT INTO `mangos`.`auctionhousebot` (`item`,`stack`,`bid`,`buyout`) "
                    f"VALUES({entry},{stack},{bid},{buyout}); -- {name}\n")
    log(f"\nwrote {a.out}  ({len(out):,} rows)")
    write_rates(a.profile, os.path.expanduser(a.out))


def write_rates(name, sql_path):
    """Emit the mangosd.conf block that matches this profile.

    The auction house is only half of how a server feels -- XP and drop rates are
    the other half, and keeping them in separate hand-edited places is how they
    drift apart. One profile, both halves.

    NB these are standard MaNGOS keys, but VERIFY against your own
    ~/vmangos/etc/mangosd.conf.dist before pasting: a key that does not exist is
    ignored silently, so a typo looks exactly like a setting that did not work.
    Requires a mangosd restart.
    """
    r = PROFILES[name]["rates"]
    d = r["drop"]
    path = os.path.join(os.path.dirname(sql_path) or ".", f"{name}.mangosd.rates.conf")
    with open(path, "w") as f:
        f.write(f"# ---- AHBot v2 profile: {name} ----\n")
        f.write(f"# {PROFILES[name]['blurb']}\n")
        f.write("# Paste into mangosd.conf (replacing the existing Rate.* lines),\n")
        f.write("# then restart mangosd. Pairs with the auction pool generated alongside.\n\n")
        for k, v in (("Rate.XP.Kill", r["xp"]), ("Rate.XP.Quest", r["quest_xp"]),
                     ("Rate.XP.Explore", r["explore_xp"]), ("Rate.Drop.Money", r["money"]),
                     ("Rate.Reputation.Gain", r["rep"]), ("Rate.Honor", r["honor"]),
                     ("Rate.Rest.InGame", r["rest"]),
                     ("Rate.Drop.Item.Poor", d["poor"]), ("Rate.Drop.Item.Normal", d["normal"]),
                     ("Rate.Drop.Item.Uncommon", d["uncommon"]), ("Rate.Drop.Item.Rare", d["rare"]),
                     ("Rate.Drop.Item.Epic", d["epic"]), ("Rate.Drop.Item.Legendary", d["legendary"]),
                     ("Rate.Drop.Item.Referenced", d["normal"])):
            f.write(f"{k} = {v:g}\n")
    log(f"wrote {path}")


def listing(it, r, rng, rumour=False):
    cls, stackable = it["class"], max(1, it["stackable"] or 1)
    if cls in STACKABLE_CLASSES and stackable > 1:
        stack = stackable if rng.random() < FULL_STACK_CHANCE else rng.randint(1, stackable)
    else:
        stack = 1

    base = max(it["sell_price"] or 0, 1)
    qv = QUALITY_VALUE.get(it["quality"], 1.0)
    d = QUALITY_DAMP.get(cls)
    if d:
        qv = 1.0 + (qv - 1.0) * d
    value = (base
             * qv
             * demand_of(it)
             * min(SCARCITY_CAP, (1.0 + r * 9.0) ** (SCARCITY_ALPHA * 3.2)))

    sigma = (SIGMA_BASE + (SIGMA_RARE - SIGMA_BASE) * r) * P["sigma_scale"]
    value *= math.exp(rng.gauss(0.0, sigma)) * P["price_scale"]
    if rumour:
        value *= rng.uniform(*RUMOUR_PRICE_MULT)

    ceiling = P.get("price_cap_g")
    hard = min(COPPER_CAP, ceiling * 10000) if ceiling else COPPER_CAP
    # Damp the compounding: a 20-stack of a rare reagent is worth more than one,
    # but not 20x a price that already includes a x110 quality premium.
    stack_factor = stack ** 0.72 if stack > 1 else 1.0
    buyout = int(min(hard, max(value * stack_factor, base * stack * 1.05, 1)))
    bid    = int(max(1, min(buyout - 1, buyout * rng.uniform(*BID_FRACTION))))
    return (it["entry"], stack, bid, buyout, (it["name"] or "").replace("\n", " "))


def report(live, rumours, stats, supply, rarity):
    log("\n" + "=" * 64)
    log(f"  eligible items      {stats['items']:,}")
    log(f"  pool rows           {stats['rows']:,}   (v1.4 produced 21,758)")
    log(f"  rumour items        {stats['rumour_items']:,} of {len(rumours):,} unreleased found")
    log(f"  rumour rows         {stats['rumour_rows']:,}")
    log("=" * 64)
    ranked = sorted(live, key=lambda x: x[1])
    log("\n  RAREST obtainable items (should be near-unbuyable):")
    for it, s in ranked[:8]:
        log(f"    {it['name'][:44]:<46} supply={s:.2e}  rarity={rarity(s):.2f}")
    log("\n  MOST ABUNDANT (should flood the house):")
    for it, s in ranked[-8:]:
        log(f"    {it['name'][:44]:<46} supply={s:.2e}  rarity={rarity(s):.2f}")


if __name__ == "__main__":
    main()
