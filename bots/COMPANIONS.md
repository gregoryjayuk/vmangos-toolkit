# Persistent companions — real characters as party bots

Written 31 Aug 2026, from the code of the core that actually runs (`6958f266`,
built 22 Aug 2026, `~/vmangos-test`). Everything below carries a `file:line`
into that tree so a later session can check rather than trust.

`.partybot add` invents a stranger who evaporates when you dismiss them.
`.partybot load <name>` logs **a real character of yours** in as a companion,
and with `PlayerBot.AllowSaving = 1` — already set — that character keeps
everything it earns. That is the whole feature. It needs no code changes.

---

## The one rule that shapes everything

```cpp
if (sWorld.FindSession(accountId))   // PlayerBotMgr.cpp:423
{
    sLog.Out(..., "[PlayerBotMgr] Account %u is already online!");
    return false;
}
```

A bot gets a real `WorldSession` built from **its character's own account id**
(`PlayerBotMgr.cpp:464`), and the server refuses to open a second session on an
account that already has one. Two consequences, and they are the reason this
document exists:

1. **A companion can never live on the account you are playing.** You are logged
   in on `PLAYER`; any character on `PLAYER` is unloadable while you play.
2. **One companion per account.** Four bots at once means four accounts.

So a full five-man is **you + four bot accounts**. A ten-man is nine.

| account | id | holds | spare for a bot? |
|---|---|---|---|
| `PLAYER` | 2 | Thornleaf, Aldric, Brann, Corwin | ❌ — the account you play |
| `ADMIN` | 1 | the GM character (admin only) | ❌ — keep it free for admin |
| `BOT1` | 4 | Dunmar — druid, 40 | ✅ |
| `BOT2` | 5 | Elric — hunter, 13 | ✅ |
| `BOT3` | 6 | **Garret** — human male warrior | ✅ |
| `BOT4` | 7 | **Isolde** — human female warlock | ✅ |
| `BOT5` | 8 | **Mirelle** — human female rogue | ✅ |

Created 31 Aug 2026. Five bot accounts, so a full five-man party plus Greg, with
one to spare. All five share one password, and all sit at gmlevel 0.

⚠ **The account names do not match the characters inside them.** Isolde the
warlock lives on `BOT4`, and Mirelle the rogue lives on `BOT5`. The account
names were chosen before the characters existed and the plan changed while they
were being made. This is harmless — only one character per account matters, and
`.partybot load` takes the *character* name — but do not assume the mapping.
The party as built: druid healer, warrior, rogue, warlock, plus Thornleaf.

---

## Step 1 — create the accounts

`account create` is `SEC_CONSOLE` (`Chat.cpp:149`): it cannot be typed in game
at any GM level, only into the server's own console, which the live config
disables. The script below starts a throwaway server against a copy of the
config with the console on, pipes the commands in, and closes stdin — which the
console turns into a clean shutdown (`CliRunnable.cpp:160`).

```bash
ssh server '~/bin/vmangos-make-bot-accounts.sh BOT1 BOT2'
```

It prompts for one password, shared by every account it makes, and reads it with
`read -rs` — never as an argument, because `argv` is world-readable via `ps(1)`.
It refuses to run if anyone is online, and refuses names that already exist. The
live server is down for about forty seconds while it works.

Bot accounts stay at `gmlevel 0` deliberately: a bot session inherits its
account's security (`PlayerBotMgr.cpp:464`), and a companion has no business
holding GM rights. A new account has no `account_access` row, which *is* level 0
— see the warning in [../GM-COMMANDS.md](../GM-COMMANDS.md) about
`account.gmlevel` being the wrong column to read or write.

## Step 2 — create the characters

Two routes. **The second is much less tedious.**

**Route A — log in as each bot account.** Start the client, log in as `BOT1`,
make the character, log out, repeat. You pick race, class, name and face at the
normal screen. Four bots is four logins.

**Route B — make them all on your own account, then move them.** You have six
free character slots on `PLAYER`. Make all four companions there in one sitting
at the normal creation screen, then hand each one to its own account:

```bash
ssh server "mariadb test_characters -e \"UPDATE characters SET account=4 WHERE name='Fenwick';\""
```

Account ids are in the table above. Only `characters.account` matters — it is
what `GetPlayerAccountIdByGUID` reads to decide which session to open. For a
tidy character-select screen, refresh the counts afterwards:

```bash
ssh server "mariadb test_realmd -e 'UPDATE realmcharacters r SET numchars=(SELECT COUNT(*) FROM test_characters.characters c WHERE c.account=r.acctid)'"
```

Moving a character back later is the same statement with `account=2`. Nothing
else in the character DB keys on account in a way that matters here.

## Step 2b — kit them out, or they are useless

🚨 **The single most important thing on this page.** A spawned bot and a loaded
bot are not set up the same way, and the difference is easy to miss until a
companion dies in the first pull.

`PartyBotAI::OnPlayerLogin` (`PartyBotAI.cpp:615`) branches on
`if (m_race && m_class)` — true only for a **temporary** bot from
`.partybot add`. That branch calls `GiveLevel`, `LearnPremadeSpecForClass`,
`AutoEquipGear` and `UpdateSkillsToMaxSkillsForLevel`. The `else // loaded from
db` branch calls **none of them.**

So `.partybot add rogue` gives you a level-matched, fully specced, geared rogue
in one line — and `.partybot load Kestrel` gives you exactly whatever that
character actually is. A fresh one is level 1, knows no spells, wears nothing and
has level-1 weapon skills. Levelling it with `.character level` does not help on
its own: that sets `level` and `xp` and nothing else (`CharacterCommands.cpp:1870`
— "all other will be updated at loading", which means *stats*, not spells or
gear).

The server already ships the fix, in `player_premade_spell_template` and
`player_premade_item_template` — the same data the spawned bots use. Two
commands apply it to a real character, and **both act on your current target**,
so the companion has to be in the world in front of you.

They are `SEC_BASIC_ADMIN`, which `PLAYER` deliberately does not have — they
would let Greg gear *himself* in one line. So this is done from the GM account,
which is exactly why it exists. Log in as the character on `ADMIN` and, per
companion:

```
.partybot load Garret                     summon it (ADMIN is gmlevel 6)
                                           then click it / target it
.character premade spec arms-39-twink      auto-levels to 39, resets talents, learns ~40 spells
.character premade gear dps-39-twink       equips a full set
.character level 40                        top up; no name needed with a target selected
.partybot remove                           saves on logout
```

Both premade commands **level the character themselves** if it is below the
template's level (`ObjectMgr.cpp:12372` and `:12415`), so a fresh level-1
character does not need levelling first — spec it, gear it, then top up to 40.

Templates top out at level 39 below 60, so **39 is the right tier for a level-40
companion**. Run either command with no argument to list what exists for the
targeted class.

| companion | class | `premade spec` | `premade gear` |
|---|---|---|---|
| Dunmar | druid | `feral-fc-39-twink` | `dps-39-twink` |
| Garret | warrior | `arms-39-twink` | `dps-39-twink` (or `tank-39-twink`) |
| Mirelle | rogue | `assa-daggers-39-twink` | `dps-39-twink` |
| Isolde | warlock | `affliction-39-twink` | `dps-39-twink` |

**Dunmar as a healer.** There is no restoration template below level 60 — the
druid line is `feral-fc` at 19/29/39/49 and only splits into feral/balance/resto
at 60. Use the feral one anyway: it carries Healing Touch (8903), Regrowth
(8941), Rejuvenation (3627), Tranquility (740), Remove Curse and Abolish Poison,
because druids learn those regardless of spec. Her *talents* will be feral, which
is not ideal, but she will have the spells the healer AI looks for. Then
`.partybot setrole healer`. At 60, swap her to `resto-swiftmend-pve`.

⚠ **`.learn all_myclass` is not a shortcut here.** It reads
`m_session->GetPlayer()` (`CharacterCommands.cpp:2705`) — it teaches *you*, not
your target, so it does nothing for a bot.

Gear template *names* repeat across classes (every class has a `dps-39-twink`);
the command matches on name **and** the target's class, so the name is
unambiguous. At 60 the same tables carry `dps-preraid-bis` and `phase6-bis` sets,
which is how these companions get re-kitted later without hand-picking items.

## Step 3 — play with them

```
.partybot load Fenwick      summon a companion into your group
.partybot setrole healer        tank / healer / dps
.partybot remove                dismiss (progress saves on logout)
```

They earn XP, quest credit, loot and reputation like anyone else — `GiveXP` has
no bot check — and it all persists.

---

## Why you can still do this at gmlevel 0

Your account lost every GM power on 31 Aug 2026, and `.partybot` is
`SEC_ADMINISTRATOR` (`Chat.cpp:1221`) — so on the face of it, de-GMing should
have taken the bots with it. It doesn't, because this core has an RBAC layer the
old one lacked:

```cpp
bool ChatHandler::isAvailable(ChatCommand const& cmd) const   // Chat.cpp:1488
{
    if (GetAccessLevel() >= (AccountTypes)cmd.SecurityLevel) { ...banned check... }
    else
    {
        auto itrGranted = m_rbacAccountGrantedPermissions.find(...);
        if (itrGranted != ... && cmd.PermissionMask & itrGranted->second)
            return true;                    // too low a level, but permitted
    }
}
```

`ExecuteCommand` checks availability on the **leaf** command only
(`Chat.cpp:1884`) — `FindCommand` walks down to the subcommand without testing
the parent — so granting each `partybot <sub>` individually is enough. All
nineteen are mapped in `test_realmd.rbac_command_permissions` under permission
`1`, and account 2 holds it. The startup log says `Loading RBAC for chat
commands...` with no `nonexistent command` lines, which is how you know all
nineteen resolved.

`battlebot` is mapped the same way as permission `2` but **not granted**. One
line turns it on:

```bash
ssh server "mariadb test_realmd -e 'INSERT INTO rbac_account_permissions VALUES (2,2,1)'"
```

⚠ **This is the one claim here not tested against a running client.** The RBAC
rows load without error and the code path is unambiguous, but proving it takes
Greg logging in and typing `.partybot add dps`. If a bot appears, it works. If it
answers **"This command is not available to you."** (`mangos_string` entry 50)
then `isAvailable` rejected it and the grant is not reaching the command — check
`ssh server 'wow errors'` for `nonexistent command` lines, and confirm
`rbac_account_permissions` still holds the `(2,1,1)` row.

---

## Living with them — loot, gear, levelling

**They pass on everything.** `SMSG_LOOT_START_ROLL` is answered with a hardcoded
`ROLL_PASS` (`CombatBotBaseAI.cpp:3420`). A bot never needs, never greeds, never
takes a drop. Every dungeon item lands with you, and you hand out what you want
them to have. There is no setting for this; it is a constant in the code.

**Trade is how you give them things, and they equip on the spot.** Bots
auto-accept: `TRADE_STATUS_BEGIN_TRADE` → accept, `TRADE_STATUS_TRADE_ACCEPT` →
accept, and on `TRADE_STATUS_TRADE_COMPLETE` they call `EquipOrUseNewItem()`
(`CombatBotBaseAI.cpp:3358–3378`). They also auto-accept resurrection and duel
requests through the same handler.

🚨 **`EquipOrUseNewItem` destroys what it replaces.** Read it
(`CombatBotBaseAI.cpp:2958`):

```cpp
uint32 slot = me->FindEquipSlot(pItem->GetProto(), NULL_SLOT, true);
if (slot != NULL_SLOT)
{
    if (Item* pItem2 = me->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
        me->DestroyItem(INVENTORY_SLOT_BAG_0, slot, true);   // <-- gone. no undo.
    ...
    me->EquipItem(slot, pItem, true);
}
```

There is **no comparison of item level, quality or stats**. Hand a bot a grey
sword and it will bin the blue it was wearing. Check before you trade — the bot
will not.

Two more behaviours from the same function:
- **Consumables are used immediately.** Anything with `ITEM_CLASS_CONSUMABLE`
  gets `CastItemUseSpell` on the spot. Do not hand a bot your potions to carry.
- **It force-learns the proficiency** for whatever you give it
  (`LearnSpell(proficiencySpellId)`), so bots can wield things their class would
  normally have to train for.
- It only scans the **backpack** (`INVENTORY_SLOT_ITEM_START`…`END`), not bags.

**They level, and it sticks.** `Player::GiveXP` has no bot check, they are real
group members for XP purposes, and `PlayerBot.AllowSaving = 1` persists it.

🚨 **But levelling teaches them nothing.** `LearnDefaultSpells()` only ever
grants the level-1 race/class kit from `playercreateinfo_spell`, and it runs at
character creation, at login and on race change — **never on level up**
(`Player.cpp:19379`). In vanilla you learn from a trainer, and a bot never visits
one. So a companion ground from 40 to 49 gains stats, health and mana, and is
still casting the same rank of everything it had at 39.

The fix is to re-apply the next premade tier from the GM account as they cross
each band — `…-49-twink` at 49, then the level-60 sets. Usefully, **the bot
re-reads its own rotation the moment it learns anything**: `SMSG_LEARNED_SPELL`,
`SMSG_SUPERCEDED_SPELL` and `SMSG_REMOVED_SPELL` all set `m_resetSpellData`
(`PartyBotAI.cpp:548–555`), which triggers `PopulateSpellData()` on the next
tick. So a spec applied mid-dungeon takes effect immediately — no reload needed.

## Roles are a flag, not a spec

`.partybot setrole healer` is authoritative. The AI branches on
`GetRole() == ROLE_HEALER` in roughly a dozen places in `PartyBotAI.cpp` and
never consults talents to decide how to behave. A feral-specced druid told to
heal *will* heal — including dropping out of cat or bear form to cast
(`PartyBotAI.cpp:2969`).

`AutoAssignRole()` (`CombatBotBaseAI.cpp:58`) only picks the **default** when you
don't say, and it does it by looking for one signature spell:

| class | test | role |
|---|---|---|
| warrior | has Shield Slam | tank, else melee dps |
| druid | has Moonkin Form | range dps |
| druid | has Leader of the Pack | melee dps |
| druid | neither | **healer** |
| priest / paladin / shaman | has Shadowform / Holy Shield / Stormstrike etc. | dps, else **healer** |
| rogue | — | melee dps |
| mage / warlock / hunter | — | range dps |

Note the consequence for Dunmar: `feral-fc-39-twink` contains neither Moonkin
Form nor Leader of the Pack (a 30-point talent she cannot reach at 39), so she
defaults to healer with no instruction at all. Set the role explicitly anyway.

What her feral talents *do* cost her is potency, not behaviour — no healing
talents, and feral leather instead of anything with spirit or intellect. She is a
real healer who is bad at it. That is a level-60 problem to fix with
`resto-swiftmend-pve`, not a reason to reroll her.

## When one dies

A dead companion **stays dead where it fell**, indefinitely, and this is by
design rather than a bug — two separate pieces of code have to agree before a bot
gets itself up, and in Greg's group neither does.

`PartyBotAI::ShouldAutoRevive` (`PartyBotAI.cpp:237`) returns false the moment any
living group member is a **healer class**, and `IsHealerClass`
(`CombatBotBaseAI.h:239`) tests class alone, ignoring spec. Thornleaf is a druid.
Dunmar is a druid. So it is false whenever either of them is standing.

And the escape hatch does not apply: the only path that releases a corpse to a
graveyard — which would flip the death state to `DEAD` and trip the
`return true` on the first line of `ShouldAutoRevive` — is guarded by
`if (me->InBattleGround())` (`PartyBotAI.cpp:733`). Outside a battleground a bot
never releases, so it never times out into a self-revive. It waits forever for a
resurrection it has decided is coming.

Three ways to get it up, cheapest first:

1. **Wait for Dunmar — she does it herself, out of combat.** Her template
   includes Rebirth (spell 20739), `PopulateSpellData` files any
   `SPELL_EFFECT_RESURRECT` as `m_resurrectionSpell`
   (`CombatBotBaseAI.cpp:1617`), and `UpdateOutOfCombatAI` casts it on any group
   corpse in range and line of sight before doing anything else
   (`PartyBotAI.cpp:919`). The Maple Seed reagent is handed to her automatically
   at spawn by `AddAllSpellReagents`. She must be alive, and it is once per
   **30 minutes** (`categoryRecoveryTime` on 20739).
2. **Cast Rebirth yourself.** Thornleaf knows 20739 as well, and bots auto-accept
   resurrection requests (`SMSG_RESURRECT_REQUEST` → `accept = true`,
   `CombatBotBaseAI.cpp:3380`). A separate 30-minute cooldown from Dunmar's, so
   between the two there are two battle-rezzes per fight.
3. **Reload it** — target the corpse, `.partybot remove`, then
   `.partybot load <name>`. No cooldown, always works. The character saves dead
   but comes back at full health: it has no ghost flag, so it loads with the
   default alive death-state (`Player.cpp:15069` only sets `DEAD` for ghosts) and
   the bot's own init calls `SetHealthPercent(100.0f)`.

⚠ `.revive` would be the obvious answer and Greg does not have it — it is
`SEC_GAMEMASTER` (`Chat.cpp:1247`) and deliberately outside the RBAC grant,
because it works on players too. Option 3 is the gmlevel-0 equivalent.

## The command set worth knowing

All nineteen are granted to `PLAYER`. Most take **your current target**; the
ones that act on the whole group say so.

| command | what it does |
|---|---|
| `.partybot pause [ms] [all]` | **Stay back.** Freezes the bot on the spot — `StopMoving` + `MoveIdle` and the AI stops ticking. Default **5 minutes** with no number. `all` = whole group. |
| `.partybot unpause [all]` | Resume. |
| `.partybot cometome` | Bot comes to you. **With no target, every bot comes.** The fix for bots stuck in geometry or standing in fire. |
| `.partybot pull [ms]` | Target a mob: **tanks attack it, DPS bots freeze** (default 10s). The controlled pull. |
| `.partybot caststop` / `caststart` | Stop a bot casting anything at all (`m_preventCasting`, and it interrupts what is in progress). This is how you stop a caster breaking your crowd control. |
| `.partybot attackstart` / `attackstop` | Point a bot at a target, or make it drop combat. |
| `.partybot aoe` | Target a mob to direct AoE at it. |
| `.partybot ccmark <mark>` | Bot crowd-controls anything wearing that raid icon. |
| `.partybot focusmark <mark>` | Bot attacks that icon first. |
| `.partybot clearmarks` | Forget both lists. |
| `.partybot setrole tank\|healer\|dps\|meleedps\|rangedps` | Re-role on the fly; re-scans the rotation immediately. |
| `.partybot unequip` | Strip its gear. |
| `.partybot remove` | Dismiss the targeted bot; saves on the way out. |

Marks are `star, circle, diamond, triangle, moon, square, cross, skull`. The
mark system is the most useful thing here and the least discoverable: mark a
caster with a skull and `focusmark skull` and the group actually focuses.

🚨 **Durations are in MILLISECONDS, despite what `pull` prints.** `pause` does
`duration = atoi(arg1)` and feeds it straight to `m_updateTimer.Reset(duration)`.
`.partybot pause 30` freezes a bot for **thirty milliseconds** — one thirtieth of
a second, indistinguishable from nothing. You want `.partybot pause 30000`.
`pull` has the same handling but its confirmation message divides by 1000 before
printing, so `.partybot pull 15` reports *"paused for 0 seconds"* and is telling
the truth. Bare `.partybot pause` and bare `.partybot pull` use sane defaults
(5 minutes and 10 seconds), so the safest habit is to pass no number at all.

## What you are actually getting

Read [SMARTER-BOTS.md](SMARTER-BOTS.md) before expecting too much. The AI is a
1 Hz fixed-priority spell ladder with no threat model, no line-of-sight check on
attacks, and no awareness of ground effects — it stands in every void zone.
Persistence makes them *yours*; it does not make them good.

Two practical notes:

- **`.partybot add` spawns at your level** (`PlayerBotMgr.cpp:880`), so
  throwaways always match you. A loaded companion is whatever level it actually
  is, so a fresh level-1 alongside Thornleaf at 40 will die constantly. Either
  level them the slow way in your party, or have the admin account gear and
  level them once as a deliberate setup step.
- The admin account for that is **`ADMIN`** (gmlevel 6). Keep it characterless
  and use it only for setup, so the temptation stays on the other side of a
  logout.

### A dead bot will not get up, and that matters more now

`PartyBotAI::ShouldAutoRevive` (`PartyBotAI.cpp:237`) refuses to self-resurrect
while **any living group member is a healer class** — and `IsHealerClass`
(`CombatBotBaseAI.h:239`) counts `CLASS_DRUID` on class alone, spec ignored.
Thornleaf is a druid. So every bot that dies near him waits forever for a
resurrection it assumes he is about to cast.

⚠ **The usual fix no longer exists for Greg.** Both `.revive` and `.revive` on a
group (`Chat.cpp:1247` and `:461`) are `SEC_GAMEMASTER`, and they are *not* in
the RBAC grant — deliberately, since a self-revive command is exactly the kind of
death-doesn't-matter lever he asked to have taken away. At gmlevel 0 the options
are: **rez it properly in game**, or **`.partybot remove` and `.partybot load`
again** — the character saves on logout, so nothing is lost by re-adding it.

If that proves too annoying in practice, the honest fix is to add `revive` to the
RBAC grant for bots only — but it works on players too, so it would hand back a
real cheat. Better to leave it out.
