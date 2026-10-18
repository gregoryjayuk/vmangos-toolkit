#!/usr/bin/env python3
"""
trial_of_four_winds.py -- generate the level-40 milestone quest for vMangos.

Greg's brief (21 Aug 2026): a quest every ten levels from the class trainer,
touring as much of the world as is survivable at that level, with collection as
well as travel, that FEELS epic and ends in an epic reward. Level 40 first.
No dungeons.

DESIGN NOTES WORTH KEEPING

* No dungeons is enforced STRUCTURALLY, not from memory: every source creature is
  filtered to map 0 (Eastern Kingdoms) or map 1 (Kalimdor). Instances have their
  own map ids, so a dungeon mob cannot slip in by accident.

* One quest, four objectives. vMangos gives `ReqItemId1..4` -- exactly four item
  slots -- and `RewChoiceItemId1..6` -- exactly six choice rewards. The whole
  shape of this quest is dictated by those two numbers. Four winds, four corners
  of the world, six weapons.

* The route crosses both continents, which at level 40 means a boat or zeppelin.
  That is the "epic" -- not mob difficulty, but the map.

* THE FERAL DRUID REWARD. In vanilla, a druid in Cat or Bear form derives damage
  from the form's base value scaled by attack power; the WEAPON'S DPS IS IGNORED
  ENTIRELY. Only its stats carry through. So for Greg's actual character a weapon
  is a stat stick and nothing else. `Heartwood of the Four Winds` is itemised for
  exactly that -- Agi/Str/Sta, zero Int, zero Spirit, nothing wasted -- while the
  other five options carry the DPS that matters to classes who swing the thing.

* POWER BUDGET, MEASURED NOT GUESSED, from item_template itself:
    - weapon DPS: 85th-percentile BLUE at this tier is 43.5; reward = 47.9 (+10%)
    - feral stats: best blue Str+Agi+Sta at ilvl 40-55 is 41 (Stoneraven);
      reward = 50, about 22% above, which is an epic's worth and no more.
  For scale, the MEDIAN real level-40 epic is 36.9 DPS -- below a good blue. So
  these beat anything genuinely available at 40 without trivialising content.
"""
import sys

Q_ENTRY   = 61001          # quest
ITEM_BASE = 61010          # quest tokens
REW_BASE  = 61100          # reward weapons
Q2_ENTRY  = 61002          # the second quest -- the guardian
TALISMAN  = 61020          # combine-result item, reward of quest 1
HEART     = 61021          # drops from the guardian
GUARDIAN  = 61200          # custom creature
# Greg, 21 Aug, mid-Stranglethorn: "you just kill stuff and collect eight tokens.
# That's not so epic." Correct. Four fetch objectives is a fetch quest with better
# scenery. So the trial now ESCALATES: gather across the world -> the four tokens
# combine into one talisman -> carry it to a windswept overlook nobody visits ->
# a guardian answers -> take what he carries back to your trainer.
#
# NOTE ON "SUMMON": Greg asked whether the talisman could spawn the mob. It cannot
# -- summoning needs SPELL_EFFECT_SUMMON and spells live in the client's Spell.dbc,
# which cannot be authored server-side. The guardian therefore stands at the cairn
# permanently; the talisman is what makes him ANSWER, which is narrative rather
# than mechanical. Same story, achievable mechanics.
#
# Quest 1's OBJECTIVES are deliberately unchanged so Greg's in-progress tokens
# survive; only its reward moves from the weapons to the talisman.
GUARDIAN_POS = (0, -4073.0, -3380.0, 372.0, 3.1)   # Grim Batol Watch Post, Wetlands
DROP_PCT  = 30.0           # feels like a hunt, not a job

# How much the quest log tells you. Greg asked whether the vagueness was
# deliberate -- it was not, it was an omission. Vanilla convention is to name the
# source ("found on the panthers of Stranglethorn"); a fetch quest that hides its
# source reads as frustrating rather than mysterious, because the discovery has
# no payoff. But it is his server, so:
# Greg's correction, and he is right: vanilla's mysterious mode is not "name the
# mob" or "say nothing" -- it is a BEARING FROM A LANDMARK. "South of the village",
# "north of the lake". You are told where to go, not what to kill, and the finding
# out is the quest. The landmarks below were derived from game_tele, not written
# from memory, so every place name is one that really exists at those coordinates.
#   "landmark" -- zone + a real bearing, no mob names   (vanilla mystery, default)
#   "creature" -- zone AND what to kill                 (vanilla explicit)
#   "zone"     -- zone only
#   "cryptic"  -- nothing but the flavour text
HINT_LEVEL = "landmark"
NEED      = 8              # of each token

# ---------------------------------------------------------------------------
# The four winds. (token entry, name, [source creature entries], zone, map)
# Creature entries and spawn counts verified against the live world DB.
# ---------------------------------------------------------------------------
WINDS = [
    (ITEM_BASE + 0, "Fang of the East Wind",  [684, 667],   "Stranglethorn Vale", 0,
     "Shadowmaw Panthers and Skullsplitter trolls, in the jungle south of Booty Bay"),
    # The whole Silvermane pack, not just the Wolf. With one source this leg had
    # 32 spawn points against Feralas's 264 -- eight times grindier, and the
    # player would have felt it as respawn-camping rather than a hunt. Balance
    # the LEGS by total spawns, not by counting mob types.
    (ITEM_BASE + 1, "Pelt of the North Wind", [2924, 2925, 2926], "The Hinterlands", 0,
     "the Silvermane pack -- wolves, howlers and stalkers, in the highland forest"),
    (ITEM_BASE + 2, "Horn of the West Wind",  [5286, 5249, 5254], "Feralas",      1,
     "Longtooth runners and the Woodpaw gnolls, across the sea"),
    (ITEM_BASE + 3, "Sting of the South Wind", [5423, 5615], "Tanaris",           1,
     "Scorpid lashers and Wastewander bandits, in the deep desert"),
]

# ---------------------------------------------------------------------------
# Rewards. subclass: 7=1H Sword, 1=2H Axe, 15=Dagger, 4=1H Mace, 2=Bow, 10=Staff
# inventory_type: 13=1H, 17=2H, 26=ranged, 21=main hand
# stats: 3=Agility 4=Strength 5=Intellect 6=Spirit 7=Stamina
# ---------------------------------------------------------------------------
TARGET_DPS = 47.9

# ATTACK POWER. Vanilla DOES have "Attack Power - Feral" -- I was wrong to say
# otherwise. But the smallest is spell 26153 at +140, worn by Mace of Unending
# Life at ilvl 70; the series does not go below that and NEW spells cannot be
# created, because spells live in the client's Spell.dbc, not the database.
# +140 on a level-40 item is roughly a 40% damage increase. So the staff carries
# GENERIC attack power instead, which in vanilla applies in Cat and Bear form
# just the same -- it simply scales to the tier.
AP_MELEE  = 9336    # "Attack Power 30"  -> +30 attack power on equip
AP_RANGED = 21437   # "Attack Power Ranged 29"

# display_id: pulled from real vanilla weapons of the matching type, because the
# first cut hardcoded one sword model onto all six and every reward looked
# identical in the quest window.
REWARDS = [
    dict(name="Heartwood of the Four Winds", sub=10, inv=17, speed=3.20,
         stats=[(3, 20), (4, 16), (7, 14)], display=24014, armor=220, spell=AP_MELEE,
         desc="The trial's true prize. Shaped for those who fight in fur and claw."),
    dict(name="Eastwind Sabre",       sub=7,  inv=13, speed=2.60,
         stats=[(3, 14), (7, 11)], display=36378, armor=0, spell=AP_MELEE,
         desc="Light, fast, and honest."),
    dict(name="Northwind Reaver",     sub=1,  inv=17, speed=3.40,
         stats=[(4, 20), (7, 15)], display=33435, armor=0, spell=AP_MELEE,
         desc="It swings like weather coming in."),
    dict(name="Westwind Fang",        sub=15, inv=13, speed=1.80,
         stats=[(3, 17), (7, 9)],  display=35819, armor=0, spell=AP_MELEE,
         desc="Quick as the thing it was named for."),
    dict(name="Southwind Cudgel",     sub=4,  inv=13, speed=2.70,
         stats=[(4, 13), (7, 12), (6, 8)], display=35574, armor=0, spell=AP_MELEE,
         desc="Desert-cured haft, iron head."),
    dict(name="Longbow of the Four Winds", sub=2, inv=26, speed=2.80,
         stats=[(3, 16), (7, 10)], display=35870, armor=0, spell=AP_RANGED,
         desc="Draws long and lets go clean."),
]


# Bearings verified against game_tele coordinates on the live world DB.
LANDMARKS = {
    0: "among the old troll ruins in the heart of the Vale, "
       "between Ziata'jai and Balia'mah",
    1: "in the high forest south-east of the Creeping Ruin, "
       "under Skulk Rock",
    2: "up in the Woodpaw Hills, north of where the Verdantis River runs",
    3: "out past the Broken Pillar, north-west of Gadgetzan",
}


def esc(s):
    return s.replace("'", "''")


def dmg(speed, dps):
    """Split a DPS target into a min/max damage band around the weapon speed.
    +/-15% spread is roughly what vanilla weapons of this tier carry."""
    avg = dps * speed
    return int(round(avg * 0.85)), int(round(avg * 1.15))


def main(out):
    L = []
    A = L.append
    A("-- The Trial of the Four Winds -- level 40 milestone quest")
    A("-- Generated by trial_of_four_winds.py. Review before importing.")
    A("-- Rollback: DELETE the entry ranges at the bottom of this file.")
    A("")

    # ---- quest tokens -----------------------------------------------------
    A("-- ============ quest tokens ============")
    for entry, name, _srcs, zone, _map, _hint in WINDS:
        A(f"DELETE FROM `item_template` WHERE `entry`={entry};")
        A("INSERT INTO `item_template` "
          "(`entry`,`class`,`subclass`,`name`,`description`,`display_id`,`quality`,"
          "`flags`,`buy_count`,`buy_price`,`sell_price`,`inventory_type`,`bonding`,"
          "`stackable`,`max_count`,`item_level`,`required_level`) VALUES"
          f"({entry},12,0,'{esc(name)}','A token of the trial. Taken in {esc(zone)}.',"
          f"5013,1,0,1,0,0,0,4,{NEED*2},{NEED*2},40,38);")
    A("")

    # ---- loot -------------------------------------------------------------
    A("-- ============ loot: overworld only (map 0/1), no dungeons ============")
    for entry, name, srcs, _zone, _map, _hint in WINDS:
        for c in srcs:
            A(f"DELETE FROM `creature_loot_template` WHERE `entry`={c} AND `item`={entry};")
            A("INSERT INTO `creature_loot_template` "
              "(`entry`,`item`,`ChanceOrQuestChance`,`groupid`,`mincountOrRef`,`maxcount`) "
              f"VALUES({c},{entry},{DROP_PCT},0,1,1);   -- {esc(name)}")
    A("")

    # ---- rewards ----------------------------------------------------------
    A("-- ============ rewards: quality 4 (epic), required level 40 ============")
    for i, r in enumerate(REWARDS):
        e = REW_BASE + i
        lo, hi = dmg(r["speed"], TARGET_DPS)
        cols = ["`entry`", "`class`", "`subclass`", "`name`", "`description`",
                "`display_id`", "`quality`", "`buy_count`", "`buy_price`", "`sell_price`",
                "`inventory_type`", "`bonding`", "`item_level`", "`required_level`",
                "`max_durability`", "`dmg_min1`", "`dmg_max1`", "`dmg_type1`", "`delay`",
                "`stackable`", "`armor`", "`spellid_1`", "`spelltrigger_1`"]
        vals = [str(e), "2", str(r["sub"]), f"'{esc(r['name'])}'", f"'{esc(r['desc'])}'",
                str(r["display"]), "4", "1", "0", "24000", str(r["inv"]), "1", "48", "40",
                "100", str(lo), str(hi), "0", str(int(r["speed"] * 1000)), "1",
                str(r["armor"]), str(r["spell"]), "1"]
        for n, (st, sv) in enumerate(r["stats"], start=1):
            cols += [f"`stat_type{n}`", f"`stat_value{n}`"]
            vals += [str(st), str(sv)]
        A(f"DELETE FROM `item_template` WHERE `entry`={e};")
        A(f"INSERT INTO `item_template` ({','.join(cols)}) VALUES({','.join(vals)});")
        feral = sum(v for s, v in r["stats"] if s in (3, 4, 7))
        A(f"--   {r['name']}: {lo}-{hi} dmg / {r['speed']}s = "
          f"{(lo+hi)/2/r['speed']:.1f} dps, Str+Agi+Sta={feral}, "
          f"armor={r['armor']}, display={r['display']}")
    A("")

    # ---- chain items ------------------------------------------------------
    A("-- ============ the talisman and the guardian's heart ============")
    for e, nm, desc in (
        (TALISMAN, "Wind-Bound Talisman",
         "Four winds, bound into one. It pulls, faintly, toward the north-east."),
        (HEART, "Heart of the Storm",
         "Still warm. Still moving, a little.")):
        A(f"DELETE FROM `item_template` WHERE `entry`={e};")
        A("INSERT INTO `item_template` "
          "(`entry`,`class`,`subclass`,`name`,`description`,`display_id`,`quality`,"
          "`buy_count`,`buy_price`,`sell_price`,`inventory_type`,`bonding`,"
          "`stackable`,`max_count`,`item_level`,`required_level`) VALUES"
          f"({e},12,0,'{esc(nm)}','{esc(desc)}',6377,3,1,0,0,0,4,1,1,45,38);")
    A("")

    # ---- the guardian -----------------------------------------------------
    A("-- ============ the guardian ============")
    A("-- Stats copied from Foulbelly (entry 2601): level 42 rare elite, hp x5,")
    A("-- dmg x2.2. A real fight for a level-40 solo, not a wall.")
    A(f"DELETE FROM `creature_template` WHERE `entry`={GUARDIAN};")
    A("INSERT INTO `creature_template` "
      "(`entry`,`name`,`subname`,`level_min`,`level_max`,`faction`,`rank`,`unit_class`,"
      "`display_id1`,`health_multiplier`,`damage_multiplier`,`armor_multiplier`,"
      "`base_attack_time`,`movement_type`,`ai_name`,`npc_flags`) VALUES"
      f"({GUARDIAN},'Skarn, the Fifth Wind','Guardian of the Trial',42,43,45,2,2,"
      "11551,5,2.2,1,2000,0,'',0);")
    A(f"DELETE FROM `creature_loot_template` WHERE `entry`={GUARDIAN};")
    A("INSERT INTO `creature_loot_template` "
      "(`entry`,`item`,`ChanceOrQuestChance`,`groupid`,`mincountOrRef`,`maxcount`) "
      f"VALUES({GUARDIAN},{HEART},100,0,1,1);")
    m, x, y, z, o = GUARDIAN_POS
    A(f"DELETE FROM `creature` WHERE `id`={GUARDIAN};")
    A("INSERT INTO `creature` "
      "(`id`,`map`,`position_x`,`position_y`,`position_z`,`orientation`,"
      "`spawntimesecsmin`,`spawntimesecsmax`,`wander_distance`,`movement_type`,"
      "`health_percent`,`mana_percent`) VALUES"
      f"({GUARDIAN},{m},{x},{y},{z},{o},300,420,5,1,100,100);")
    A("")

    # ---- the quest --------------------------------------------------------
    A("-- ============ the quest ============")
    details = (
        "There is a test older than any I can teach you, and it is not a test of arms.\\n\\n"
        "Four winds cross this world, and each carries something back to those who go and "
        "stand in it. The east wind smells of wet jungle. The north wind comes down off the "
        "highlands with frost still in it. The west wind has crossed an ocean to reach you. "
        "And the south wind is dry enough to crack a lip.\\n\\n"
        "Go and stand in all four. Bring me proof of each. Do not hurry -- the point is the "
        "going, not the arriving.\\n\\n"
        "When you have all four, come back to me. There is one thing after that, and it is "
        "not a wind you can stand in."
    )
    objectives = ("Bring proof of all four winds: Stranglethorn Vale, the Hinterlands, "
                  "Feralas, and Tanaris.")
    # Rewritten 22 Aug 2026: this text was written when the quest handed over the
    # weapon directly. It now gives the talisman and sends the player on, so
    # "Take one" was offering a choice that does not happen here.
    offer = ("You went. That is most of it.\\n\\n"
             "Hold them together. There -- four winds, one weight. Feel how it pulls? "
             "North and east, toward the mountain.\\n\\n"
             "There is a fifth wind, and it does not move. Go and find out what stands in it.")
    request = "Four winds. Have you stood in them all?"

    cols = ["`entry`", "`Method`", "`ZoneOrSort`", "`MinLevel`", "`QuestLevel`", "`Type`",
            "`SuggestedPlayers`", "`QuestFlags`", "`Title`", "`Details`", "`Objectives`",
            "`OfferRewardText`", "`RequestItemsText`", "`RewXP`", "`RewOrReqMoney`"]
    vals = ["61001", "2", "-1", "38", "40", "0", "1", "8",
            "'The Trial of the Four Winds'", f"'{details}'", f"'{esc(objectives)}'",
            f"'{offer}'", f"'{esc(request)}'", "5400", "9000"]
    for n, (entry, name, _s, zone, _m, hint) in enumerate(WINDS, start=1):
        if HINT_LEVEL == "landmark":
            text = f"{name} -- {zone}, {LANDMARKS[n-1]}"
        elif HINT_LEVEL == "creature":
            text = f"{name} -- {zone}: {hint}"
        elif HINT_LEVEL == "zone":
            text = f"{name} ({zone})"
        else:
            text = name
        cols += [f"`ReqItemId{n}`", f"`ReqItemCount{n}`", f"`ObjectiveText{n}`"]
        vals += [str(entry), str(NEED), f"'{esc(text)}'"]
    cols += ["`RewItemId1`", "`RewItemCount1`", "`NextQuestInChain`", "`NextQuestId`"]
    vals += [str(TALISMAN), "1", str(Q2_ENTRY), str(Q2_ENTRY)]
    A(f"DELETE FROM `quest_template` WHERE `entry`={Q_ENTRY};")
    A(f"INSERT INTO `quest_template` ({','.join(cols)}) VALUES({','.join(vals)});")
    A("")

    # ---- quest 2: the guardian ---------------------------------------------
    # ⚠ ONE objective, not two. The first cut had BOTH "slay Skarn"
    # (ReqCreatureOrGOId1) and "obtain Heart of the Storm" (ReqItemId1). The Heart
    # is a 100% drop and comes from nothing else, so the kill objective was pure
    # redundancy -- and it read in the quest log as a second, separate thing to do.
    # Worse: the Heart's loot chance is POSITIVE, so it drops for anyone whether or
    # not they hold the quest. Kill Skarn before accepting quest 2 and you end up
    # holding the item with no kill credit and an objective you can never tick.
    # Possessing the Heart IS proof of the kill. Do not re-add the kill line.
    A("-- ============ quest 2: The Fifth Wind ============")
    d2 = ("Four winds you have stood in. There is a fifth, and it does not move.\\n\\n"
          "Take the talisman north-east, to the old watch post above Grim Batol, where "
          "the wind comes off the mountain and does not stop. Something waits there that "
          "has waited a long time. It will not trouble you until you hold the talisman "
          "up, and then it will trouble you a great deal.\\n\\n"
          "Bring me what it carries.")
    o2 = "Take the Wind-Bound Talisman to the overlook above Grim Batol and face what answers."
    or2 = ("So it answered.\\n\\nThen the trial is finished, and the choice is yours. "
           "Take one, and know that the road put it in your hand, not me.")
    c2 = ["`entry`", "`Method`", "`ZoneOrSort`", "`MinLevel`", "`QuestLevel`", "`Type`",
          "`SuggestedPlayers`", "`QuestFlags`", "`PrevQuestId`", "`SrcItemId`", "`SrcItemCount`",
          "`Title`", "`Details`", "`Objectives`", "`OfferRewardText`", "`RequestItemsText`",
          "`ReqItemId1`", "`ReqItemCount1`", "`ObjectiveText1`",
          "`RewXP`", "`RewOrReqMoney`"]
    v2 = [str(Q2_ENTRY), "2", "-1", "38", "42", "0", "1", "8", str(Q_ENTRY),
          str(TALISMAN), "1",
          "'The Fifth Wind'", f"'{d2}'", f"'{esc(o2)}'", f"'{or2}'",
          "'Does it still beat?'",
          str(HEART), "1", "'Heart of the Storm'",
          "6200", "12000"]
    for n, r in enumerate(REWARDS, start=1):
        c2 += [f"`RewChoiceItemId{n}`", f"`RewChoiceItemCount{n}`"]
        v2 += [str(REW_BASE + n - 1), "1"]
    A(f"DELETE FROM `quest_template` WHERE `entry`={Q2_ENTRY};")
    A(f"INSERT INTO `quest_template` ({','.join(c2)}) VALUES({','.join(v2)});")
    A("")

    # ---- questgiver -------------------------------------------------------
    A("-- ============ questgiver: every class trainer ============")
    A("-- Greg's instinct, and it is right: the trainer is the one NPC every")
    A("-- character actually visits. trainer_type=0 is the class trainer flag;")
    A("-- npc_flags & 16 is TRAINER. Both relations so it is given AND turned in")
    A("-- wherever you happen to be when you finish.")
    A(f"DELETE FROM `creature_questrelation` WHERE `quest` IN ({Q_ENTRY},{Q2_ENTRY});")
    A(f"DELETE FROM `creature_involvedrelation` WHERE `quest` IN ({Q_ENTRY},{Q2_ENTRY});")
    # DISTINCT is load-bearing: creature_template carries one row per content
    # PATCH, so a plain SELECT entry returns the same creature several times and
    # the insert dies on the (id,quest) primary key partway through -- leaving
    # the relations half-populated, which is worse than failing outright.
    A("INSERT INTO `creature_questrelation` (`id`,`quest`) "
      f"SELECT DISTINCT `entry`,{Q_ENTRY} FROM `creature_template` "
      "WHERE `npc_flags` & 16 AND `trainer_type`=0;")
    for q in (Q_ENTRY, Q2_ENTRY):
        A("INSERT INTO `creature_involvedrelation` (`id`,`quest`) "
          f"SELECT DISTINCT `entry`,{q} FROM `creature_template` "
          "WHERE `npc_flags` & 16 AND `trainer_type`=0;")
    A("INSERT INTO `creature_questrelation` (`id`,`quest`) "
      f"SELECT DISTINCT `entry`,{Q2_ENTRY} FROM `creature_template` "
      "WHERE `npc_flags` & 16 AND `trainer_type`=0;")
    A("")
    A("-- ============ rollback ============")
    A(f"-- DELETE FROM `quest_template` WHERE `entry`={Q_ENTRY};")
    A(f"-- DELETE FROM `creature_questrelation` WHERE `quest`={Q_ENTRY};")
    A(f"-- DELETE FROM `creature_involvedrelation` WHERE `quest`={Q_ENTRY};")
    A(f"-- DELETE FROM `item_template` WHERE `entry` BETWEEN {ITEM_BASE} AND {REW_BASE+99};")
    A(f"-- DELETE FROM `creature_loot_template` WHERE `item` BETWEEN {ITEM_BASE} AND {ITEM_BASE+9};")

    open(out, "w").write("\n".join(L) + "\n")
    print(f"wrote {out}  ({len(L)} lines)")
    print(f"  quest {Q_ENTRY} · {len(WINDS)} tokens · "
          f"{sum(len(w[2]) for w in WINDS)} loot entries · {len(REWARDS)} rewards")
    for r in REWARDS:
        lo, hi = dmg(r["speed"], TARGET_DPS)
        feral = sum(v for s, v in r["stats"] if s in (3, 4, 7))
        print(f"  {r['name']:<30} {(lo+hi)/2/r['speed']:>5.1f} dps  Str+Agi+Sta={feral}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "trial_of_four_winds.sql")
