# GM commands — a vMangos build

Read from the source at commit **`e0966fca`**, which was the exact build running on
the server when this was written (the hash is in the binary's own strings). This
describes *your* server, not a generic wiki.

- Tree: `src/game/Chat/Chat.cpp` · Levels: `AccountTypes` in `src/shared/Common.h`
- **727 commands**, 713 available to you, 14 console-only

> ⚠ **Two things below went stale on 31 Aug 2026. Read this before using the file.**
>
> **1. It describes the retired binary.** The live core is now `6958f266` (built
> 22 Aug, `~/vmangos-test`). The command tree is close but not identical — this
> build added the RBAC layer described in
> [bots/COMPANIONS.md](bots/COMPANIONS.md), which `e0966fca` had no trace of. Any
> single command should be confirmed with `.help <command>` in game.
>
> **2. The account model is inverted.** This file used to say: *"Your GM account
> is `PLAYER`, `gmlevel = 6` (Administrator). `ADMIN`, `BOT1` and `BOT2` have
> no GM access."* On the live realm the truth is now the opposite, at Greg's
> request — he wanted to be able to die:
>
> | account | gmlevel | |
> |---|---|---|
> | `ADMIN` | **6** | the admin account. Characterless on purpose. |
> | `PLAYER` | **0** | Greg's play account. No GM commands at all. |
> | `BOT1`, `BOT2` | 0 | spare accounts, usable as bot homes |
>
> 🚨 **The GM level lives in `account_access`, NOT in `account.gmlevel`.** The
> `account.gmlevel` column exists, is writable, looks authoritative and is read
> by **nothing** — the server joins `account_access` on
> `RealmID IN (-1, <realm>)` to get security (`WorldSocket.cpp:289`,
> `AccountMgr.cpp:549`), and `AccountMgr::SetSecurity` writes only there
> (`AccountMgr.cpp:213`). A missing row means level 0. This bit during the
> 31 Aug cutover: `UPDATE account SET gmlevel=0` reported four rows changed and
> left Greg a full Administrator. To change a level, do this and restart:
>
> ```bash
> # grant: id 1 becomes Administrator on realm 1
> ssh server "mariadb test_realmd -e 'REPLACE INTO account_access (id,gmlevel,RealmID) VALUES (1,6,1)'"
> # revoke: no row = SEC_PLAYER
> ssh server "mariadb test_realmd -e 'DELETE FROM account_access WHERE id=2'"
> ```
>
> To read the *effective* level, always join — never `SELECT gmlevel FROM account`:
>
> ```bash
> ssh server "mariadb test_realmd -e \"SELECT a.username, COALESCE(aa.gmlevel,0) AS gmlevel FROM account a LEFT JOIN account_access aa ON a.id=aa.id AND aa.RealmID IN (-1,1)\""
> ```
>
> `PLAYER` keeps exactly one exception: the nineteen `.partybot` subcommands,
> granted through RBAC rather than through gmlevel. Nothing else on this page
> works on it — not `.gm on`, not `.cheat god`, not `.tele`, not `.additem`.
> What still works at level 0 is `.help`, `.commands`, `.save`, `.unstuck`,
> `.start`, `.dismount`, `.server info`, `.server motd`, `.account …`,
> `.gm ingame` and `.wr`; `.modify xprate` exists but is pinned to 1.0 by
> `Rate.XP.Personal.Min`/`Max`, so it cannot be used to level faster.
>
> Note also that `account create`, `account delete`, `account set gmlevel` and
> `account set password` are **`SEC_CONSOLE`** — unreachable from chat even at
> gmlevel 6. See [bots/COMPANIONS.md](bots/COMPANIONS.md) for the console route.

⚠ The `command` table in the DB holds only **2 rows** — it is for *overrides*. The real
list is compiled into the binary, which is why this had to come from source.

`.help <command>` in game gives the syntax for any single command.

## Privilege levels

| level | name | |
|---|---|---|
| 0 | Player |  |
| 1 | Moderator |  |
| 2 | Ticketmaster |  |
| 3 | Gamemaster |  |
| 4 | Basic Admin |  |
| 5 | Developer |  |
| 6 | Administrator | you have this |
| 7 | Console only | server terminal only — you cannot reach these from chat |

## Start here

| command | what it does | lvl |
|---|---|---|
| `.modify speed 5` | Run five times faster. 1 is normal, 10 is the cap. | 2 |
| `.gm on` | GM mode: nothing attacks you, and you can target anything. | 3 |
| `.cheat god` | Take no damage at all. | 3 |
| `.lookup item Thunderfury` | Find an item's ID by name. Do this before .additem. | 2 |
| `.additem 19019 1` | Give yourself an item by ID. | 3 |
| `.levelup 5` | Gain five levels. Negative numbers go down. | 4 |
| `.learn all_myclass` | Learn every spell your class can have at your level. | 3 |
| `.tele booty` | Teleport to a named location. .lookup tele finds names. | 1 |
| `.go xyz -4073 -3380 372` | Teleport to raw coordinates — how you reach Skarn. | 2 |
| `.partybot add druid` | Spawn a bot party member. The one worth exploring. | 3 |
| `.npc add 61200` | Spawn a creature by ID where you stand. | 3 |
| `.revive` | Resurrect yourself or your target on the spot. | 2 |
| `.unstuck` | Free yourself if the world has trapped you. | 0 |
| `.modify scale 0.5` | Change your size. Purely cosmetic, entirely worth it. | 3 |
| `.repairitems` | Repair everything you're wearing. | 3 |
| `.quest complete 61001` | Force-complete a quest by ID. | 3 |

---

## Yourself

*Stats, speed, cheats, appearance — the things you point at your own character.*

- `.aoedamage` *(lvl 3)*
- `.aura` *(lvl 4)*
- `.bank` *(lvl 2)*
- `.charge` *(lvl 3)*
- **`.cheat`** *(lvl 3)* — `castchecks`, `casttime`, `cooldown`, `criticals`, `debuffs`, `debugtargetinfo`, `fixedz`, `fly`, `god`, `ignoretriggers`, `immunenpc`, `immunepc`, `powercost`, `procs`, `status`, `triggerpass`, `untargetable`, `wallclimb`, `waterwalk`
- `.combatstop` *(lvl 3)*
- **`.cooldown`** *(lvl 3)* — `clear`, `clearclientside`, `list`
- `.damage` *(lvl 3)*
- `.demorph` *(lvl 3)*
- `.deplenish` *(lvl 3)*
- `.die` *(lvl 3)*
- `.dismount` *(lvl 0)*
- `.explorecheat` *(lvl 2)*
- `.fear` *(lvl 3)*
- `.freeze` *(lvl 2)*
- **`.gold`** *(lvl 4)* — `remove`
- **`.groupspell`** *(lvl 6)* — `add`, `rule`
- `.hidearea` *(lvl 2)*
- `.hover` *(lvl 2)*
- `.knockback` *(lvl 3)*
- **`.learn`** *(lvl 1/2/3/5/6)* — `all`, `all_crafts`, `all_default`, `all_gm`, `all_items`, `all_lang`, `all_myclass`, `all_myspells`, `all_mytalents`, `all_mytaxis`, `all_recipes`, `all_trainer`
- `.levelup` *(lvl 3)*
- `.maxskill` *(lvl 3)*
- **`.modify`** *(lvl 0/2/3/4)* — `accessories`, `agility`, `ap`, `arcane`, `armor`, `aspeed`, `block`, `boundrad`, `bwalk`, `castspeed`, `combreach`, `crit`, `dodge`, `drunk`, `emotestate`, `energy`, `exhaustion`, `faction`, `fire`, `fly`, `frost`, `gender`, `haircolor`, `hairstyle`, `holy`, `honor`, `hp`, `intellect`, `mainspeed`, `mana`, `money`, `morph`, `mount`, `nature`, `offspeed`, `parry`, `rage`, `rangeap`, `rangecrit`, `rangespeed`, `rep`, `scale`, `shadow`, `skincolor`, `speed`, `spellcrit`, `spellpower`, `spirit`, `stamina`, `strength`, `swim`, `tp`, `xprate`
- `.mount` *(lvl 3)*
- `.nameaura` *(lvl 4)*
- `.possess` *(lvl 3)*
- `.pvp` *(lvl 3)*
- `.removeriding` *(lvl 3)*
- `.repairitems` *(lvl 3)*
- `.replenish` *(lvl 3)*
- **`.reset`** *(lvl 3/5/6)* — `all`, `honor`, `items`, `level`, `spells`, `stats`, `talents`
- `.revive` *(lvl 3)*
- `.save` *(lvl 0)*
- `.setskill` *(lvl 3)*
- `.showarea` *(lvl 2)*
- `.stable` *(lvl 2)*
- `.taxicheat` *(lvl 2)*
- `.unaura` *(lvl 3)*
- `.unfreeze` *(lvl 2)*
- **`.unlearn`** *(lvl 3)* — `all_crafts`, `all_gm`, `all_recipes`
- `.unstuck` *(lvl 0)*

## Getting around

*Teleporting yourself, your target, or your group.*

- `.angle` *(lvl 1)*
- `.cometome` *(lvl 3)*
- `.distance` *(lvl 1)*
- **`.go`** *(lvl 2)* — `alterac`, `arathi`, `creature`, `forward`, `graveyard`, `grid`, `object`, `relative`, `target`, `taxinode`, `trigger`, `up`, `warsong`, `xy`, `xyz`, `xyzo`, `zonexy`
- `.gocorpse` *(lvl 2)*
- `.goname` *(lvl 2)*
- `.gps` *(lvl 1)*
- `.groupgo` *(lvl 2)*
- `.guid` *(lvl 1)*
- `.linkgrave` *(lvl 5)*
- `.namego` *(lvl 2)*
- `.neargrave` *(lvl 2)*
- `.recall` *(lvl 1)*
- **`.tele`** *(lvl 2/5)* — `add`, `del`, `group`, `name`

## Items

*Spawning and removing gear.*

- `.additem` *(lvl 3)*
- `.additemset` *(lvl 3)*
- `.deleteitem` *(lvl 3)*
- `.itemmove` *(lvl 3)*

## Creatures & NPCs

*Spawning, editing, moving and scripting mobs.*

- **`.escort`** *(lvl 2/5)* — `addwp`, `clearwp`, `create`, `hidewp`, `modwp`, `showwp`
- `.movegens` *(lvl 2)*
- `.namedie` *(lvl 3)*
- **`.npc`** *(lvl 1/2/3/5)* — `additem`, `addweapon`, `aiinfo`, `allowattack`, `allowmove`, `delitem`, `despawn`, `evade`, `follow`, `group add`, `group addrel`, `group del`, `group link`, `info`, `move`, `playemote`, `say`, `set displayid`, `set entry`, `set faction`, `set flag`, `set level`, `set movetype`, `set reactstate`, `set respawntime`, `set wanderdistance`, `spawn add`, `spawn addentry`, `spawn delete`, `spawn info`, `spawn move`, `spawn set auras`, `spawn set deathstate`, `spawn set displayid`, `spawn set emotestate`, `spawn set entry`, `spawn set movetype`, `spawn set respawntime`, `spawn set sheathstate`, `spawn set standstate`, `spawn set wanderdistance`, `summon`, `tame`, `textemote`, `unfollow`, `whisper`, `yell`
- **`.pet`** *(lvl 1/3/5)* — `delete`, `info`, `learnspell`, `list`, `loyalty`, `rename`, `unlearnspell`
- `.respawn` *(lvl 4)*
- **`.unit`** *(lvl 1/5)* — `aiinfo`, `factioninfo`, `info`, `moveinfo`, `show class`, `show combattimer`, `show createspell`, `show emotestate`, `show form`, `show gender`, `show miscflags`, `show moveflags`, `show npcflags`, `show powertype`, `show race`, `show sheathstate`, `show standstate`, `show unitflags`, `show unitstate`, `show visflags`, `speedinfo`, `statinfo`, `ufinfo`
- **`.wp`** *(lvl 2/5/6)* — `add`, `export`, `modify`, `show`

## World objects

*Gameobjects, spawn pools, triggers and instances.*

- **`.event`** *(lvl 3/4/5)* — `disable`, `enable`, `list`, `start`, `stop`
- **`.gobject`** *(lvl 2/3/5)* — `add`, `customanim`, `delete`, `despawn`, `despawnanim`, `info`, `move`, `near`, `reset`, `respawn`, `select`, `setgostate`, `setlootstate`, `spawnanim`, `target`, `tmpadd`, `toggle`, `turn`, `ufinfo`, `use`
- **`.instance`** *(lvl 2/3/4)* — `continents`, `getdata`, `groupunbind`, `listbinds`, `perfinfos`, `savedata`, `smartrebind`, `stats`, `switch`, `unbind`
- **`.mmap`** *(lvl 3/6)* — `connect`, `loadedtiles`, `loc`, `path`, `reload`, `stats`, `testarea`, `unload`
- **`.pool`** *(lvl 3/6)* — `list`, `spawns`, `update`
- **`.trigger`** *(lvl 2)* — `active`, `near`

## Quests

*Adding, completing and removing quests.*

- **`.honor`** *(lvl 2/4)* — `add`, `addkill`, `reset`, `setrp`, `show`
- **`.quest`** *(lvl 3/4)* — `add`, `complete`, `remove`, `status`
- **`.wareffort`** *(lvl 5)* — `getresource`, `info`, `setgongtime`, `setresource`, `setstage`

## Bots

*Party members, battleground bots, and the auction house bot.*

- **`.ahbot`** *(lvl 6)* — `reload`, `update`
- **`.battlebot`** *(lvl 6)* — `add alterac`, `add arathi`, `add warsong`, `remove`, `removeall`, `showallpaths`, `showpath`
- **`.bot`** *(lvl 6)* — `add`, `add_all`, `delete`, `info`, `ranadd`, `reload`, `start`, `stop`
- **`.partybot`** *(lvl 6)* — `add`, `aoe`, `attackstart`, `attackstop`, `ccmark`, `clearmarks`, `clone`, `cometome`, `focusmark`, `load`, `pause`, `pull`, `remove`, `setrole`, `unequip`, `unpause`, `usegobject`

## Finding things

*Looking up IDs and listing what exists — where most sessions start.*

- `.commands` *(lvl 0)*
- `.groupinfo` *(lvl 2)*
- `.help` *(lvl 0)*
- **`.list`** *(lvl 2)* — `auras`, `clicktomove`, `creature`, `exploredareas`, `hostilerefs`, `item`, `maps`, `movegens`, `object`, `talents`, `threat`
- **`.lookup`** *(lvl 1/2/3/4)* — `account email`, `account ip`, `account iponline`, `account name`, `area`, `creature`, `creaturemodel`, `event`, `faction`, `guild`, `item`, `itemset`, `object`, `player account`, `player character`, `player email`, `player ip`, `player name`, `pool`, `quest`, `skill`, `sound`, `spell`, `taxinode`, `tele`
- `.pinfo` *(lvl 2)*

## Server & accounts

*Administration, moderation, and the world itself.*

- **`.account`** *(lvl 0/3/6/7)* — `characters`, `cleardata`, `create`, `delete`, `lock`, `onlinelist`, `password`, `set addon`, `set gmlevel`, `set locked`, `set password`
- `.announce` *(lvl 4)*
- `.anticheat` *(lvl 2)*
- **`.antispam`** *(lvl 2/4)* — `add`, `remove`, `removereplace`, `replace`
- **`.auction`** *(lvl 2)* — `alliance`, `goblin`, `horde`
- **`.ban`** *(lvl 2/3/6)* — `account`, `allip`, `character`, `ip`, `note`, `warn`
- **`.baninfo`** *(lvl 2/3)* — `account`, `character`, `ip`
- **`.banlist`** *(lvl 2/3)* — `account`, `character`, `ip`
- **`.bg`** *(lvl 3)* — `start`, `status`, `stop`
- **`.channel`** *(lvl 1)* — `join`, `leave`
- **`.character`** *(lvl 1/2/3/4/5/6/7)* — `aiinfo`, `citytitle`, `clean items`, `clean todelete`, `deleted delete`, `deleted list account`, `deleted list name`, `deleted old`, `deleted restore`, `erase`, `fillflys`, `hasitem`, `level`, `premade gear`, `premade savegear`, `premade savespec`, `premade spec`, `race`, `rename`, `reputation`, `skin`
- **`.cinematic`** *(lvl 5)* — `addwp`, `gotime`, `listwp`
- **`.gm`** *(lvl 0/1/2/3/6)* — `chat`, `fly`, `ingame`, `list`, `setview`, `visible`
- **`.group`** *(lvl 3)* — `additem`, `replenish`, `revive`, `summon`
- **`.guild`** *(lvl 3/4)* — `create`, `delete`, `invite`, `rank`, `rename`, `uninvite`
- `.kick` *(lvl 2)*
- `.log` *(lvl 3)*
- `.mute` *(lvl 1)*
- `.notify` *(lvl 4)*
- **`.pbcast`** *(lvl 6)* — `setthreads`, `stats`
- **`.pdump`** *(lvl 6)* — `load`, `write`
- `.quit` *(lvl 7)*
- **`.reload`** *(lvl 5/6)* — `account_banned`, `all`, `all_area`, `all_gossips`, `all_item`, `all_locales`, `all_loot`, `all_npc`, `all_quest`, `all_scripts`, `all_spell`, `anticheat`, `areatrigger_involvedrelation`, `areatrigger_tavern`, `areatrigger_teleport`, `autobroadcast`, `character_pet`, `cinematic_waypoints`, `command`, `conditions`, `config`, `creature`, `creature_ai_events`, `creature_battleground`, `creature_display_info_addon`, `creature_groups`, `creature_involvedrelation`, `creature_loot_template`, `creature_onkill_reputation`, `creature_questrelation`, `creature_spells`, `creature_spells_scripts`, `creature_template`, `disenchant_loot_template`, `event_scripts`, `exploration_basexp`, `fishing_loot_template`, `game_graveyard_zone`, `game_tele`, `game_weather`, `gameobject`, `gameobject_battleground`, `gameobject_involvedrelation`, `gameobject_loot_template`, `gameobject_questrelation`, `gameobject_requirement`, `gameobject_scripts`, `gameobject_template`, `generic_scripts`, `gossip_menu`, `gossip_menu_option`, `gossip_scripts`, `instance_buff_removal`, `ip_banned`, `item_enchantment_template`, `item_loot_template`, `item_required_target`, `item_template`, `locales_creature`, `locales_gameobject`, `locales_gossip_menu_option`, `locales_item`, `locales_page_text`, `locales_points_of_interest`, `locales_quest`, `mail_loot_template`, `mangos_string`, `map_loot_disabled`, `map_template`, `npc_gossip`, `npc_text`, `npc_trainer`, `npc_vendor`, `page_text`, `pet_name_generation`, `petitions`, `pickpocketing_loot_template`, `player_factionchange_items`, `player_factionchange_mounts`, `player_factionchange_quests`, `player_factionchange_reputations`, `player_factionchange_spells`, `points_of_interest`, `quest_end_scripts`, `quest_greeting`, `quest_start_scripts`, `quest_template`, `reference_loot_template`, `reputation_reward_rate`, `reputation_spillover_template`, `reserved_name`, `skill_fishing_base_level`, `skinning_loot_template`, `spell_area`, `spell_chain`, `spell_disabled`, `spell_elixir`, `spell_group`, `spell_group_stack_rules`, `spell_learn_spell`, `spell_mod`, `spell_pet_auras`, `spell_proc_event`, `spell_proc_item_enchant`, `spell_script_target`, `spell_scripts`, `spell_target_position`, `spell_threats`, `taxi_path_transitions`, `trainer_greeting`, `variables`
- `.saveall` *(lvl 6)*
- **`.send`** *(lvl 1/6)* — `items`, `mail`, `mass items`, `mass mail`, `mass money`, `message`, `money`
- **`.server`** *(lvl 0/6/7)* — `corpses`, `exit`, `idlerestart cancel`, `idleshutdown cancel`, `info`, `log filter`, `log level`, `motd`, `plimit`, `resetallraids`, `restart cancel`, `set motd`, `shutdown cancel`
- **`.service`** *(lvl 6)* — `del_characters`
- `.sniff` *(lvl 6)*
- **`.spamer`** *(lvl 1/2)* — `list`, `mute`, `unmute`
- `.start` *(lvl 0)*
- **`.ticket`** *(lvl 2/3/6)* — `assign`, `close`, `closedlist`, `comment`, `complete`, `counter`, `delete`, `escalate`, `escalatedlist`, `list`, `next`, `notify`, `onlinelist`, `previous`, `reload`, `reset`, `response append`, `response appendln`, `response reset`, `togglesystem`, `unassign`, `viewid`, `viewname`
- **`.unban`** *(lvl 6)* — `account`, `character`, `ip`
- `.unmute` *(lvl 2)*
- `.variable` *(lvl 5)*
- **`.video`** *(lvl 3)* — `expendables`, `turn`
- `.wchange` *(lvl 4)*
- `.whispers` *(lvl 1)*
- **`.world`** *(lvl 6)* — `cansee`, `detail`, `update`
- `.wr` *(lvl 0)*

## Debug & development

*Spell/aura internals and engine diagnostics.*

- **`.cast`** *(lvl 5)* — `back`, `dist`, `self`, `target`
- **`.debug`** *(lvl 2/3/5/6/7)* — `anim`, `assert`, `bg`, `bytes1`, `bytes2`, `chatfreeze`, `condition`, `control`, `faceme`, `factionchange_items`, `forceupdate`, `getitemstate`, `getitemvalue`, `getprevplaytime`, `getvaluebyindex`, `getvaluebyname`, `loottable`, `los allow`, `los check`, `lrecipient`, `moditemvalue`, `modvalue`, `monster`, `movedistance`, `moveflags`, `movemotion`, `movespline`, `moveto`, `play cinematic`, `play music`, `play sound`, `play text`, `pvpcredit`, `send buyerror`, `send channelnotify`, `send chanvisual`, `send chanvisualnext`, `send chatmmessage`, `send equiperror`, `send impact`, `send mailerror`, `send opcode`, `send openbag`, `send poi`, `send qinvalidmsg`, `send qpartymsg`, `send sellerror`, `send spellfail`, `send visual`, `send worldstate`, `setaurastate`, `setitemvalue`, `setprevplaytime`, `setvaluebyindex`, `setvaluebyname`, `spellcheck`, `spellcoefs`, `spellmods`, `time`, `unitstate`, `utf8overflow`
- **`.spell`** *(lvl 3/5)* — `effects`, `iconfix`, `info`, `search`

