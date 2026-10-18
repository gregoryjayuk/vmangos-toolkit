# Smarter bots — review & possibilities

Written 22 Aug 2026, from a line-by-line review of the bot code the server actually runs
(vmangos `e0966fca`, the exact commit behind the June-2025 binaries on the server), plus a
survey of what the rest of the WoW-emulation world has built as of this month. Facts below
carry `file:line` references into that tree so a later session can verify instead of
trusting.

> ⚠ **31 Aug 2026: the running core is no longer `e0966fca`.** Greg retired that
> install and now plays `6958f266` (`~/vmangos-test`). The *findings* below were
> spot-checked against the new tree that day and still hold — `PlayerBots/` is
> substantially the same code — but **the `file:line` references no longer
> resolve.** They have drifted (`HandlePartyBotLoadCommand` moved from
> `PlayerBotMgr.cpp:990` to `:1002`) and some files have moved outright
> (`src/game/Server/CharacterHandler.cpp` is not at that path any more). Re-grep
> for the symbol in `~/vmangos-test/core/src`; do not trust a line number here.
>
> The section below on persistent bots is no longer theoretical: it is set up and
> written down in **[COMPANIONS.md](COMPANIONS.md)**. `PlayerBot.AllowSaving` is
> `1` on the live server, and the non-obvious constraint that turned out to shape
> everything — **one bot per account, never the account you are playing** — is
> documented there.

**The one-paragraph verdict:** PartyBot/BattleBot are ~15,600 lines of hand-rolled C++
inside the core — not plugins — and they are *reflex machines*: fixed-priority spell
ladders on a hard-coded 1-second tick, with no threat awareness, no line-of-sight checks
on attacks, no ground-AOE awareness, and no chat understanding at all. Nothing about the
server's design prevents any of the things you want — persistent named companions that
level up, LLM-driven personalities, dungeon awareness — and several of them are closer
than they look: **persistent bots on real accounts already exist behind one config flag
and one command**, and the core already ships libcurl + a JSON library + a worker-thread
pattern, so an Ollama chat integration needs zero new dependencies. The single real
prerequisite for everything else is standing up a **build pipeline** — the method so far
(BUILDING.md) has been DB-only, and bot behaviour is the first thing that needs the C++
recompiled.

**The north star (Greg, 22 Aug 2026):** PvP that feels real; raids and dungeons that
actually work; companions that quest and level; Ironforge and Stormwind that feel alive;
trade-channel banter, guild chat, party chat, whispers — and the occasional quiet /say
from someone standing next to you. Every layer below is judged against that, and each
must be a foundation for the next, not a dead end.

---

## 1. What runs today

Three bot systems share one base (`src/game/PlayerBots/`, 15,599 lines):

| System | Invocation | What it is |
|---|---|---|
| **PartyBot** | `.partybot add <class\|dps\|healer\|tank>`, `clone`, `load <name>` | Combat companion in your group. Follows, fights, heals, buffs. |
| **BattleBot** | `.battlebot add <bg> <faction>`, or `BattleBot.AutoJoin` | Battleground filler for WSG / AB / AV, waypoint-driven. |
| **RandomBot** | `RandomBot.Enable` + `playerbot` DB table | World-population shells. Conf comment is honest: "no AI". |

Facts that shape everything else:

- **Spawned bots are throwaways.** `.partybot add` invents a character in memory —
  name from the *succubus pet name generator* (`PlayerBotAI.cpp:79`), random face,
  synthetic account id that exists in no table — and `Player::Create` hard-wires
  `m_saveDisabled = true` (`Player.cpp:395`). They never touch the characters DB and
  evaporate on removal. This is why you get a random stranger every time.
- **But DB-backed bots are already supported.** `.partybot load <name>` logs an
  existing offline character in *as a party bot* (`PlayerBotMgr.cpp:990`), and with
  `PlayerBot.AllowSaving = 1` its progress **saves on logout**
  (`CharacterHandler.cpp:498`). Nothing in the core blocks bots from earning XP, quest
  credit, loot or reputation — `Player::GiveXP` has no bot check. Persistence was built;
  it's just off and undocumented.
- **The AI tick is 1 Hz and one-action-per-tick.** `PB_UPDATE_INTERVAL = 1000`
  (`PartyBotAI.cpp:40`); nearly every cast `return`s out of the tick. A bot buffs a
  5-man one buff per second and reacts to anything up to a second late. ⚠ The conf
  comment for `PlayerBot.UpdateMs` claims it controls responsiveness — **it doesn't**;
  it only throttles the manager's login/queue loop (`PlayerBotMgr.cpp:220`). The real
  cadence is a compile-time constant.
- **All control is GM dot-commands** (`.partybot pull / ccmark skull / focusmark / pause
  / cometome …`, table at `Chat.cpp:94–114`). No bot parses chat: nothing in
  `PlayerBots/` handles `SMSG_MESSAGECHAT`. The marks system (focus/CC by raid icon) is
  genuinely useful and nobody discovers it.
- **Bots receive real packets.** A bot session has no socket, and every packet the
  server would have sent to the client is diverted to
  `PlayerBotAI::OnPacketReceived` (`WorldSession.cpp:123–141`) — whispers, party chat,
  say/yell all arrive there today and are ignored. The AI also holds a raw `Player*`
  and full server-side API access. Perception is not the problem; using it is.
- Rotation completeness varies by class but the skeleton is the same everywhere:
  fixed-priority `if (CanTryToCastSpell) DoCastSpell` ladders, populated by **matching
  English spell names** at spawn (`CombatBotBaseAI.cpp:239–1601`).

## 2. Why they wipe the group — the specific dumbness

Everything below is a code fact, not an impression. The ones marked 🐛 are outright bugs.

**Positioning & movement**
1. **Zero AOE / ground-effect awareness.** No reference to `DynamicObject` (the object
   class ground AOEs are made of) anywhere in `PlayerBots/`. Bots stand in every void
   zone and breath cone for the whole fight.
2. **No line-of-sight or reachability check on attacks** (`CombatBotBaseAI.cpp:2120,
   2748`) — bots lock onto and spam-cast at mobs through walls. (BattleBot checks LOS;
   PartyBot never got the memo.)
3. **"Run away" slides through geometry.** Kiting uses raw `MonsterMove` straight-line
   splines with no pathfinding (`PartyBotAI.cpp:172–181`) — bots glide through walls
   and off ledges.
4. **Casters walk into melee** unless the fight happened to start at range
   (`PartyBotAI.cpp:341–344`); follow formation is a random 3–6 yd blob re-rolled
   every re-follow — healers stand in the cleave with everyone else.

**Threat & pulls**
5. **DPS has no threat awareness at all.** The only `ThreatManager` read in the entire
   tree is a veto on *AoE* casts (`PartyBotAI.cpp:296–305`). Single-target DPS will rip
   aggro off the tank forever; Fade/Feint/Cower are never used for threat.
6. **Tanks ping-pong between loose mobs.** The "defend party members" logic
   (`PartyBotAI.cpp:940–947`) does a full `AttackStop` + hard swap every second there's
   a mob on someone else — swing resets, no threat established on anything, no
   tab-target add pickup, taunt as an afterthought.
7. **No pull discipline.** Target selection takes anything attacking any member within
   50 yd, or whatever the leader attacks, and chases it through neighbouring packs.
   Nothing models a mob's aggro radius before walking (the API exists:
   `Creature::GetAttackDistance`, `Creature.cpp:2114` — unused by bots).

**Awareness & reactions**
8. **Interrupts only fire on the bot's own current target** — a caster mob the party
   isn't focused on channels freely. Enemy cast introspection (spell, target, time
   remaining) is fully available server-side (`SpellCaster.h:344`, `Spell.h:405–414`).
9. **Feared/stunned = total shutdown**, including the tick after control returns
   (`PartyBotAI.cpp:701`).
10. **Out-of-combat bots refuse to act until their own bars are 100%.** `DrinkAndEat`
    blocks the whole tick (`PartyBotAI.cpp:183–233, 765`) — a healer at 99% mana sits
    drinking while a member bleeds at 40%. At >100 yd from the leader they cheat: bars
    set to max, then GM-teleport onto you (`:769–791`).

**Loadouts & rotations**
11. **Random, sticky loadouts.** Paladin blessing, shaman totem-per-element, mage sheep
    variant, rogue poisons, warlock pet, hunter pet species — all rolled once at spawn.
    A healer shaman can be locked on Fire Resistance Totem for life. Rogues pick 5-point
    finishers *uniformly at random* (Expose Armor on a boss, sure).
12. 🐛 **Warlocks Demonic Sacrifice their own pet mid-fight** whenever it's off cooldown
    (`PartyBotAI.cpp:2250`); 🐛 priest's Divine Spirit picks a target then casts on
    itself (`:1884`); 🐛 assigning any CC mark silently disables that bot's AoE forever,
    even after the mark dies (`:273`).
13. **Loot is always passed, gear never changes after spawn** (`CombatBotBaseAI.cpp:3230`)
    — nothing to look forward to, and clone-quality gear decays as you level past it.

**BattleBots specifically**
14. **AB bots wander at random** — `StartNewPathToObjective` has WSG and AV cases but
    **no Arathi Basin case at all** (`BattleBotWaypoints.cpp:2031–2179`); they cap
    whatever banner they physically stumble over.
15. **Nothing defends anything in WSG** (no flag-return, no base guard); AV has the only
    defence logic (Horde: nearest assaulted objective; Alliance: a 25% dice roll).
16. **Routing is single-hop.** 77 hand-authored paths / 1,027 nodes, joined only when
    endpoints sit within 5 yd; there is **no graph search** — if no single authored path
    spans bot→objective it falls back to a uniform random walk. (Two AB junctions are
    5.7 yd apart and connect only by luck.)
17. 🐛 **Mages sheep their own kill target** — selects the off-target, casts on the
    current victim (`BattleBotAI.cpp:1883–1893`). Bots also sit down to eat mid-BG,
    never use racials or a stun-break trinket, and target nearest-enemy with no
    healer/HP priority.
18. **PartyBot and BattleBot each carry a full private copy of every class rotation**
    (~1,900 duplicated lines each; the base class declares all 20 hooks pure-virtual,
    `CombatBotBaseAI.h:141–160`) — every rotation fix must be made twice.

## 3. The prerequisite: a build pipeline (one-time cost)

Everything beyond §4's config flips is C++. The estate has never compiled this tree —
the binaries were built June 2025 on the desktop and copied. Two workable shapes:

- **Build on the server** (recommended). It's a small Intel mini-PC (2c/4t), 7.4 GB
  RAM, 176 GB free NVMe — measured today, better than the "fanless 2-core" reputation.
  First build ~1 h with `-j3`; **with ccache, incremental rebuilds are minutes**, which
  is what bot iteration actually needs. Add a swapfile before the first link. Deploy is
  already solved: install to `~/vmangos/bin`, `systemctl --user restart
  vmangos-mangosd`. Known trap if building the *pinned* tree: its
  `cmake_minimum_required(3.1...3.20)` predates Arch's CMake 4;
  `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` is the advertised escape hatch (unproven here —
  registry stub, 11 Aug). Building *current upstream* avoids the issue entirely.
- **Disposable test realm from the nightly backup.** The backup chain (04:32 dumps →
  a synced folder) means a full test server — world + characters — can be stood up
  in a Linux container on the MacBook or on the server on alternate ports, wrecked freely,
  and rebuilt in minutes. Bot experiments never need to touch the live realm until
  they're proven.

**Patch-vs-upgrade decision that comes first:** upstream vmangos has kept polishing
these exact bots since March 2025 — loot-nearby-corpses, unified chasing, spell-cooldown
manager, dispel prioritisation, CC fixes, revive-before-logout, temporary/permanent
battlebots — with no architectural change. Upgrading the core to current `development`
first buys those fixes free, keeps future merges cheap, and puts you on a tree that
builds with modern toolchains; the cost is schema migrations against the live DBs
(vmangos ships them; nightly verified backups + the test-realm loop make this a
rehearsable, reversible operation, not the leap it was in August). The alternative —
patching the pinned tree — is fine for a first experiment but compounds divergence with
every change. **Recommendation: rehearse the upgrade on a test realm, then patch on top
of current upstream, in a git fork, one branch per feature.**

## 3b. The foundation question — is vMaNGOS even the right core? (asked 22 Aug 2026)

Greg picked vMaNGOS from a YouTube video, not a comparison. For vanilla 1.12 there are
exactly two serious candidates (AzerothCore/mod-playerbots has the best bots in the
scene but is **WotLK 3.3.5** — different client, different era; TrinityCore likewise):

- **vMaNGOS** (current): Nostalrius lineage, very authentic, and it is *his world* —
  the seeded economy, the Four Winds chain, the backups, the ops knowledge. Bots:
  primitive (this whole document).
- **CMaNGOS-classic + the playerbots module**: equally mature vanilla core, and its
  bots are the **decade-matured ike3 engine** — random bots that genuinely quest,
  level, travel and populate the world; a strategy engine with dungeon/raid logic;
  chat-command control; **native LLM chat hooks already in its config**
  (`AiPlayerbot.LLMApiEndpoint`…). Against the north star above, most of the
  "living world" line is closest-to-done there, today.

Switching costs, honestly: world content ports (the generators are Python emitting
SQL — re-targeting the dialect is medium work); the 6 characters have no clean
converter (recreate with GM commands in an evening); ops shape is identical
(mangosd/realmd/MariaDB — BUILDING.md thinking transfers). Staying costs too: the
living-world tier on vMaNGOS is a season of bespoke work the other core ships free.

**Resolution path — don't decide on paper.** Stand up cmangos-classic + playerbots as
a disposable test realm (container on the MacBook, or side ports on the server), point a
client at it, and spend one evening inside it: watch the world be populated, run a
dungeon with a bot group, try the LLM chat. Then pick the foundation with evidence.
The no-compile tier below is cheap and reversible on vMaNGOS meanwhile; **the C++ tier
is what must wait for this decision.** (A binary repack like ShadowCore is not a
foundation — no source, no patches.)

## 4. Free wins — no compile, doable today

1. **`PlayerBot.AllowSaving = 1`** + create real characters for the roster (§5) —
   persistence exists behind this flag.
2. **`PartyBot.AutoEquip = 2`** (premade gear templates) — the random-gear roulette is
   half of why bots feel weak. Templates live in world-DB tables
   (`player_premade_item_template` / `player_premade_spell_template`,
   `ObjectMgr.cpp:11666`) — authorable SQL, same loop as the quests: sane per-class
   gear/spec sets at levels 20/30/40/50/60 instead of random blues with wrong stats.
3. **The PCP addon** (github.com/pumpan/PCP, built for vmangos partybots) — an in-game
   control panel over the dot-commands: attack/come/stay, focus + CC marks, paladin
   blessings, totem control. Its sibling **FillRaidBots** adds one-click dungeon/raid
   group presets. This is the biggest control-surface upgrade available for zero server
   changes.
4. **Learn the marks system** (or let PCP drive it): `.partybot ccmark moon` +
   `.partybot focusmark skull` is real kill-order + CC discipline that already works.
5. `.partybot clone` on yourself gives a bot your actual gear/spells — a better-geared
   companion than the random roll, today.

## 5. The persistent company — named bots that level (your idea, and it's close)

The plumbing exists; what's missing is convenience and personality.

**Works today (config + client, no code):**
1. Create a dedicated bot account per companion (`.account create` at the console) —
   one *online* bot per account is the constraint (one session per account).
2. Log in as each once, create the character properly — name, race, class, face. These
   are real rows in the characters DB, backed up nightly like yours.
3. Set `PlayerBot.AllowSaving = 1`.
4. In game: `.partybot load Aelwynn` — she joins, fights, **earns XP**, and saves on
   dismissal. Levels persist. You could even log into her account and play her
   yourself; she's a real character.

**Worth a small patch each (after the pipeline exists):**
- **Level-up competence:** on ding, auto-train class spells and spend talents along the
  premade-spec template (the template reader exists; it's applied only at spawn today).
- **Gear progression:** stop auto-passing loot — greed when an item is an upgrade for
  the bot's role, auto-equip on win. Suddenly dungeon runs progress *them* too, which is
  most of the reason to get to know a companion.
- **`.partybot roster` / summon-by-name** — sugar over `load` so the company can be
  called without remembering account juggling; plus out-of-dungeon idle homes (park
  them in an inn, or wandering Stormwind via the population-AI machinery) so you bump
  into them between runs.
- The `playerbot` table (`characters.sql:867`) already maps char → named AI class via
  `CreatePlayerBotAI` — the designed slot for per-character AI/personality binding.

## 6. Talking bots — the local-LLM layer

**Architecture that fits this core** (all seams verified in the tree):

```
party/whisper chat → OnPacketReceived (SMSG_MESSAGECHAT case — currently unhandled)
  → small command parser first ("follow", "wait here", "sheep moon", "oom?")  [free: no LLM]
  → else: context snapshot → request queue
      → worker thread (exact MailerService.h pattern; NEVER block a map thread)
      → libcurl POST → Ollama /api/chat on the LAN     [curl + nlohmann/json already in tree]
  → reply lands in a mutex slot → next AI tick → me->Say(...) with a typing delay
```

- **Endpoint is a conf key** (`LLM.Endpoint`, `LLM.Model`, timeout, on/off), so the
  brain can live on whatever is switched on. Ranking of the estate (checked 22 Aug):
  **M3 MacBook** — best quality/speed when it's around (Ollama, 8B-class, ~1–2 s
  replies masked by a typing delay). **The Jetson (8 GB kit, unused — probably an Orin Nano 8GB; confirm with
  `cat /etc/nv_tegra_release`)** — the dedicated companion-brain box: 7–15 W,
  headless, runs 7–8B quantised at conversational speed if it's the Orin; Greg's own
  "plug it in when I play" pattern fits it exactly, and it finally gives that box a
  job (it could host Whisper for dictation later — same box, two frictions removed).
  **the server** — 1B-model dim fallback at best. **The desktop is out** — integrated
  Vega only, no discrete GPU. Endpoint down → bots go quiet or use canned lines;
  combat never depends on chat.
- **Personality & memory per character:** a small characters-DB table keyed by guid —
  name, a personality card, a rolling LLM-maintained summary of shared history ("we
  wiped twice in Deadmines; Greg pulled the whole shipyard") refreshed after each
  session. This + the persistent roster is what turns "a bot" into "Aelwynn".
- **Context in the prompt:** identity card, zone, group composition, combat state,
  last N chat lines, recent events (level-up, boss kill, wipe, rare drop). All server-side
  reads; ~500 tokens.
- **Prior art to crib from** (all open source): `mod-ollama-chat` (AzerothCore — async
  threads, DB personalities, distance/channel filters); `cmangos/playerbots` has native
  LLM chat config (endpoint-agnostic HTTP with prompt templates — the config vocabulary
  is worth copying); `Hokken/mod-llm-chatter` (DB-queue + external Python bridge —
  zero server-thread involvement). Nobody has done it for vmangos; you'd be first.
- **A decoupled variant worth considering:** keep the C++ patch to ~50 lines — the
  packet-forwarder plus one console-allowed `.bot say <name> <text>` command — and run
  the whole brain (LLM calls, personalities, memory, even event-driven banter) as a
  **Python daemon on the MacBook** talking to the server over its built-in SOAP
  interface (`MaNGOSsoap.cpp:93` — plain HTTP POST + basic auth, `SOAP.Enabled`,
  port 7878, currently off). Compile once, iterate personalities in Python forever.
  Given how you already work — generators on the Mac, server as target — this shape is
  probably yours. ⚠ Bind SOAP to 127.0.0.1 and tunnel over the existing ssh route;
  it runs commands at console level.
- **Chat as a command channel comes free:** once bots parse chat at all, "Aelwynn,
  sheep the moon one" beats `.partybot ccmark moon` — the LLM can even map loose
  phrasing onto the existing command set (the mod-ollama-bot-buddy experiment does
  exactly this on AzerothCore; treat it as inspiration, not dependency — reflexes stay
  C++, the LLM only issues directives at human speed).

## 7. The combat brain — what "smarter" decomposes into

Ordered by wipe-prevention per line of code; every sensor named is confirmed present.

| # | Fix | Mechanism | Size |
|---|---|---|---|
| 1 | **250 ms tick** + allow 2–3 actions/tick | change `PB_UPDATE_INTERVAL`, restructure the `return`-ladders slightly | S |
| 2 | **Threat throttle for DPS** | read `ThreatManager` (`ThreatManager.h:178`): stay <90% of tank threat, else stop/Feint/Fade | S |
| 3 | **Tank stickiness + add pickup** | drop the hard-swap; hold current, taunt/mock loose mobs from the threat list, face away from the party | M |
| 4 | **LOS + reachability on hostile targets** | add `IsWithinLOSInMap` + `PathFinder` result to `IsValidHostileTarget` | S |
| 5 | **Interrupt priority** | scan nearby casters' current spells (`GetCurrentSpell`), rotate interrupts across bots, not just own-target | M |
| 6 | **Get out of fire** | grid-search `DynamicObject`s (first-class searchable, `GridNotifiers.h:206`) + enemies' in-flight AOE dest (`Spell::m_targets` has the landing point) → sidestep via `PathFinder`, back to role position after | M |
| 7 | **Pull discipline** | before chasing: check path corridor for non-engaged mobs within their `GetAttackDistance`; leash to leader | M |
| 8 | **Role positioning** | melee behind (except tank), casters camp max range, healer mid, spread 8 yd when >2 ranged | M |
| 9 | **Healer sanity** | don't drink at 99%; pre-move into heal range/LOS; dispel priority list; drink at <30% between pulls | S–M |
| 10 | **Bug batch** | mage self-sheep, warlock pet sacrifice, priest Divine Spirit, CC-mark-kills-AoE, rogue finisher table, per-role totem/blessing sets instead of random | S |

Then one **data-driven layer** on top, which is where your authoring workflow shines:
a `bot_creature_tactics` world table — `creature_id → flags` (tank_faces_away,
spread_out, kill_adds_first, dont_stand_in_front, interrupt_spell_ids, burn_priority,
avoid_ground_aoe_radius…) — interpreted by generic C++ once, then **every dungeon's
tactics become SQL you can write per-boss** with the same generate→sync→import→restart
loop as the quests. The server can even read a boss's own EventAI script
(`creature_ai_events` is queryable in-core, `CreatureEventAIMgr.h:37`) to know what's
coming — omniscient, but you own the server; dial the cheating to taste.

BattleBots, when you care: give routing a real graph search (the hub graph is small —
10/8/46 hubs measured for WSG/AB/AV), write the missing AB objective case, add WSG
defence roles and healer-first targeting, fix the sheep bug. AB is one `switch` case
away from being a different game.

## 7b. Raid scale — 9, 19, 39 at once? (asked 22 Aug 2026)

**Yes at every scale, including 39 — the box is not the constraint.** Measured same day:
mangosd idles at 1.4 GB RSS of 7.4 GB; `PlayerLimit = 100` already covers a 40-man.
The engine's own evidence: upstream ships **Alterac Valley battlebots — 80 bots in one
map** is a supported configuration, on an engine designed for 2006 server hardware.
Bots are cheaper than real players where 40 players actually hurt: a bot session has no
socket, so the movement-packet flood is skipped at the broadcaster
(`PlayerBroadcaster.cpp:52`). Raid groups with these bots are a walked path — the
FillRaidBots addon exists precisely to fill vmangos raids.

What actually limits 39, in order:
1. **One-time creation grind** — one online bot per account ⇒ 39 accounts (console-
   scriptable) + 39 hand-made characters. A small `.partybot create <name> <class>`
   patch (let a spawned bot save once) would make roster creation instant.
2. **The 1 Hz tick goes from annoyance to structural** — buff rounds take minutes at
   40; the 250 ms tick (§7 #1) is near-mandatory at raid scale.
3. **AI-vs-content is the real ceiling** — MC/Ony are forgiving and become genuinely
   doable after the wipe-killer batch + a few tactics-table rows; AQ40/Naxx mechanics
   are what the full tactics layer is for.

Pragmatic shape: a **persistent named core** (the 9 you know) + throwaway
`.partybot add` fillers for 20/40s — mixed groups are fine, both are just party bots
to the server. Promote fillers to the roster as personalities earn it.

## 8. Wilder ideas (a menu, not a plan)

- **Questing companions:** mirror the leader — auto-accept/turn-in what you accept,
  assist objectives, need-roll their own quest items. (Full autonomous questing like
  mod-playerbots is a season-sized project; *companionship* questing is a medium patch.)
- **A living world:** your roster idles in cities via the population-AI machinery when
  not summoned; guildmates online at odd hours; the guild chat has banter (LLM, cheap).
- **In-game mail from the company** — vanilla's mail API + a nightly LLM job: letters
  referencing what you actually did together. Absurdly high charm per line of code.
- **Possess-a-bot:** any roster character is a real account — log in as your tank some
  evening and let a bot heal *you*.
- **A protocol-level external bot** (headless 1.12 client driven from Python/Rust —
  gtker's `wow_srp`/`wow_messages` implement the vanilla protocol, `namigator` does
  client-side pathfinding from your map files, `wowchat` proves stable clientless
  sessions): architecturally elegant — server untouched, brain fully external — but
  you'd reimplement perception the server-side AI gets free. Keep as plan B; note
  `Anticheat.Botting.Enable = 1` would need a whitelist for it.
- **Eluna-VMaNGOS** (Eluna-Ports org, tracking vmangos, pushed Jul 2026): a maintained
  fork adding Lua scripting — not a bot engine, but if you ever want scriptable NPC
  events/quests without recompiles, the option exists and could be layered under the
  same bot patches.

## 9. What I'd actually do, in order

1. **Roster now** (§4/§5, an evening, no compile): `AllowSaving=1`, bot accounts, named
   characters, premade gear templates, PCP addon. You get persistent, named,
   levelling companions this weekend — mute and dim, but *yours*.
2. **Prove the build** (a day): fork + clone on the server, ccache, build current
   upstream, stand up the test realm from a nightly dump, rehearse the DB migration
   there, then upgrade live. (Fallback: build the pinned tree with the CMake policy
   flag and defer upgrading.)
3. **Wipe-killer batch** (§7 #1–4 + #10, a weekend of code): faster tick, threat
   throttle, tank stickiness, LOS, bug batch. This alone changes dungeon nights from
   "babysitting" to "playing".
4. **The chat seam** (§6, a weekend): packet case + parser + worker thread + Ollama on
   the MacBook; personality table; canned-line fallback. First conversation with
   Aelwynn.
5. **Fire-dodging + interrupts + positioning** (§7 #5–9), then the **tactics table**
   (§7 layer 2) authored per-dungeon as you actually run them.
6. **BG pass** (§7 tail) whenever PvP nights become a thing.

Each step is independently shippable and independently enjoyable; nothing blocks on a
grand rewrite. The characters DB stays safe throughout — bots only write it behind
`AllowSaving`, and the nightly dump has your back either way.

---

### Sources & further reading

- This tree: `src/game/PlayerBots/{PlayerBotMgr,PlayerBotAI,CombatBotBaseAI,PartyBotAI,BattleBotAI,BattleBotWaypoints}.{h,cpp}`
- Upstream: github.com/vmangos/core (active; bot fixes through 2026)
- Addons for these exact bots: github.com/pumpan/PCP · pumpan/FillRaidBots
- State of the art elsewhere: github.com/cmangos/playerbots (ike3 lineage + native LLM
  chat config) · github.com/liyunfan1223/mod-playerbots (AzerothCore, per-boss raid
  strategies) · DustinHendrickson/mod-ollama-chat · Hokken/mod-llm-chatter ·
  DustinHendrickson/mod-ollama-bot-buddy (experimental LLM-drives-actions)
- Protocol route: github.com/gtker/wow_messages · gtker/wow_srp · namreeb/namigator ·
  fjaros/wowchat
- Lua fork: github.com/Eluna-Ports/Eluna-VMaNGOS

---

## Why a dead party bot stays dead — and it's because you're a druid

Found 22 Aug 2026 when Greg asked how to revive one. Read from
`src/game/PlayerBots/PartyBotAI.cpp` at commit `e0966fca`.

A party bot self-resurrects **only** when `ShouldAutoRevive()` returns true. Outside a
battleground that needs **all** of:

1. its corpse already released (`GetDeathState() == DEAD`) — which short-circuits to true; or
2. **no group member in combat**, **and**
3. **no living HEALER-CLASS member in the group**, **and**
4. a living group member **within 15 yards**.

```cpp
if (pMember->IsInCombat())                    return false;
if (pMember->IsAlive()) {
    if (IsHealerClass(pMember->GetClass()))   return false;   // <-- this one
    if (me->IsWithinDistInMap(pMember, 15.0f)) alivePlayerNearby = true;
}
```

⚠ **`IsHealerClass()` includes `CLASS_DRUID`** (`CombatBotBaseAI.h:237` — paladin, priest,
shaman, druid). **Greg plays a feral druid.** So while he is alive and in the group, condition
3 always fails and his bots will *never* self-revive. The code assumes the living healer in
the party will handle it. Feral spec is irrelevant — the check is on CLASS, not on whether
the player can actually cast a resurrection.

This is not a bug and not worth patching; it just needs knowing.

**How to revive one, in order of least effort:**

| | |
|---|---|
| `.revive` with the bot targeted | GM command, instant, works anywhere |
| Cast **Revive** on it (out of combat) or **Rebirth** (in combat) | what the code expects a druid to do |
| `.partybot remove` then `.partybot add <class>` | nuclear — loses its gear and state |

If it had *already released* to a graveyard it would have revived on its own, since state
`DEAD` short-circuits the whole check. So the failure mode is specifically: bot dies, corpse
not released, healer-class player alive nearby, bot waits forever.

**Bots also resurrect each other** — a bot with a resurrection spell will cast it on a dead
group member via `SelectResurrectionTarget()` (`PartyBotAI.cpp:442`), but never on itself
(*"Can't resurrect self"*), and only on targets in state `CORPSE`.
