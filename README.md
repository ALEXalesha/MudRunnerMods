# MudRunnerMods

OpenTrail: gameplay mods for Spintires: MudRunner, built from the game's own files, plus the tools that build and check them.

> Not affiliated with or endorsed by Saber Interactive or Focus Entertainment. "Spintires: MudRunner" is their trademark. The mods are fan-made and for single player.

[Русская версия](README.ru.md)

The repository holds no game files. `tools/build_mods.py` reads the class XML from the installed game (`Media.zip` and the four DLC archives), changes only what a mod needs and writes one override package per mod. After a game update, run the build again.

## The mods

Ten ideas, nine mods. The fog of war cannot be removed with game files (see "Not possible").

**The six truck mods add NEW trucks and never touch a stock truck file.** Each changed truck is a full copy of the stock one under its own name, `<prefix>_<stock name>` (for example `otf_kamaz4310`), with the stock selection icon and its own display name, "C-4310 (Big Tank)" (in Russian "C-4310 (Большой бак)"). (Until 11.10 we thought the game refused stock truck files from an extra package; the crash dumps showed the real cause, a package name longer than 16 characters, see "The real cause of the crashes". Full copies stay: they leave the stock trucks and saves alone.) Pick the new trucks in the truck slots when you start a map, or spawn them in the Proving Ground; the trucks placed on the maps stay stock. Grippy Wheels, Winch Anchors and Unlocked Trucks replace stock wheel, plant and level files (wheels and plants were tested in game and work).

| Mod | New trucks | Name in the game (English / Russian) |
|---|---|---|
| Hyper Power | `oth_<truck>`, 36 | "C-4310 (Hyper)" / "C-4310 (Гипермощь)" |
| Powerful Engines | `otp_<truck>`, 36 | "C-4310 (Powerful)" / "C-4310 (Мощный мотор)" |
| AWD and Diff Lock | `ota_<truck>`, 10 (the trucks that lack AWD or a switchable diff lock) | "B-130 (AWD)" / "B-130 (Полный привод)" |
| Deep Fording | `otw_<truck>`, 36 | "C-4310 (Deep Fording)" / "C-4310 (Глубокий брод)" |
| No Damage | `otd_<truck>`, 36 | "C-4310 (No Damage)" / "C-4310 (Без поломок)" |
| Big Fuel Tank | `otf_<truck>`, 36 | "C-4310 (Big Tank)" / "C-4310 (Большой бак)" |
| your own set (`Собрать свой мод.bat`, `tools/combine.py`) | `otc_<truck>`: all chosen truck changes on one truck | "C-4310 (Custom)" / "C-4310 (Свой набор)" |

36 = every drivable truck, 20 of the base game and 16 of the DLC. Names: the game reads `<ModStrings>` only for Steam Workshop items (the exe opens `<item id>.xml`), so a local package carries a new strings file per language, `strings/<lang>/opentrail_<mod>.txt`, in the format of the game's own `assets.txt` (UTF-16, `/key` line, name line). The game lists `strings/<lang>/*.txt` itself (`china.txt` exists in two languages only and its name is not in the exe), so no stock strings file is replaced. If the game refuses such a file (`install_local.py --probe names` tells), `build_mods.py --no-names` builds the packages without names.

| Mod (package) | What it changes | Covers |
|---|---|---|
| Hyper Power (`opentrail_hyper.zip`) | `Motor@Torque` x10, capped at 1,000,000 (the game's limit), and `AngVel` of every forward gear x2 (at most 32). For fun. Replaces Powerful Engines; opt-in | 36 drivable trucks, base + DLC |
| Powerful Engines (`opentrail_power.zip`) | `Motor@Torque` x3 (stock 16,000 to 240,000) and `AngVel` of every forward gear x1.5 (at most 32): stronger and faster in every gear | 36 trucks |
| AWD and Diff Lock (`opentrail_awd.zip`) | Wheels with `Torque="none"` or no Torque get `full`; `DiffLockType="None"` becomes `Default` (switchable) | 10 trucks without AWD or a switchable diff lock |
| Deep Fording (`opentrail_ford.zip`) | `Damage@SensationMin/Max` box moved 1 m above its old top (0.2 m tall) | 36 trucks |
| No Damage (`opentrail_damage.zip`) | `Damage@Capacity` 64,000, the game's maximum (stock 160 to 1000) | 36 trucks |
| Big Fuel Tank (`opentrail_fuel.zip`, id infinite_fuel) | `TruckData@FuelCapacity` x4 (stock 40-800 l become 160-3200 l) | 36 trucks |
| Grippy Wheels (`opentrail_grip.zip`) | `WheelFriction@SubstanceFriction` x2.5, at least 2.5; `@BodyFriction` x1.5, at least 2.0 | 50 wheel types |
| Winch Anchors (`opentrail_winch.zip`) | `GameData/WinchSocket` on 7 stumps and small trees that had none | 7 plant classes |
| Unlocked Trucks (`opentrail_unlock.zip`, 295 MB) | `isLocked` cleared in the truck records of the level files | 24 trucks and trailers on 6 maps |

### Why some mods work the way they do

**Powerful Engines and Hyper Power: felt in every gear (16.10).** In-game test: "the real gain is only in 5th gear, below it as usual". Cause in the gearbox code of MudRunner.exe (0x140922270): a gear gets `Torque / sqrt(max(AngVel/2, 1))` (the high gear `Torque x 1.25`), times a curve of the driven wheels' speed that rises up to `AngVel` and falls to ZERO at `2 x AngVel + 5` rad/s (high gear `AngVel + 2`). Above that speed the gear gives nothing, however strong the engine. A light truck reaches that end in gears 1-4 with the stock engine already, so torque x2.5 alone changed nothing there; in 5th (A-469 AngVel 20, end 45 rad/s) stock torque ran out first, so the gain showed. Now the mods raise the speed of every forward gear and the high gear too: Powerful Engines `AngVel` x1.5 and `Torque` x3, Hyper Power `AngVel` x2 and `Torque` x10 (at most 1,000,000); `AngVel` at most 32, the exe limit (0x1408a07f5). The formula gives a faster gear a bit less torque; the torque factor pays it back. The law `test_power_mods_are_felt_in_every_gear` computes with the exe's formula per truck and gear: gear torque at least x2.4 (Hyper Power x2.9), band end x1.5 (x2), reverse stock; the formula's numbers are read from the exe (`test_gear_rules_match_the_exe`). The "small jerks" in low gears: the same function cuts torque when a wheel spins up too fast (probably by `MaxDeltaAngVel`); that part is not fully read and not changed.

**The big tank does not make a truck heavier (16.10).** In-game test: "goes slowly and feels very heavy". By the files the copy `otf_<truck>` is the stock truck except `FuelCapacity` (A-469 mass 1600 kg, centre of mass, engine, wheels - compared for every copy). By the exe fuel adds weight only through a `<FuelMass><Body Mass=.../></FuelMass>` block (reader 0x1408c93b9, 'fuel mass body'), and only cisterns have one. The law `BigTankMassTest`: the copies have no FuelMass, stock mass and centre of mass. So the copy should not be slower than the stock A-469; the A-469 itself is weak (torque 40,000, a KamAZ 140,000). Stronger with a big tank: your own set "Big Fuel Tank + Powerful Engines" (below).

**Big Fuel Tank (was Infinite Fuel), and why not 64,000 l.** No file sets fuel consumption, so the mod makes the tank bigger. Infinite Fuel 1.0.0 used 64,000 l (the exe maximum) and trucks jerked and did not move (11.10). Cause, read in MudRunner.exe: the game works with the fill = litres / FuelCapacity; below 0.06 it cuts the engine at random every tick with chance 1 - fill/0.06 (0x1409224a5, the "last litres" cough), below 0.2 it shows the red warning (0x1407b3e73). A truck from the profile or a save brings its fuel in LITRES (SetFuel 0x1408cbde0 from desc.fFuel), and a fuel station adds litres; only the parked trucks of a level file get a percentage. So a full stock tank (at most 800 l) was 1.25 % of 64,000 - the cough zone. The law (tests/test_limits.py FuelFillLawTest, thresholds read from the exe): a full stock tank must be at least 25 % of the new one, so the tank is x4.

**No Damage uses a huge capacity, not 0.** The game divides damage by `Capacity` (the damage factor in `truck.lua` and the `Damage: %d/%d` display). 0 would divide by zero, the ETS2 lesson where fuel consumption 0 gave `-nan` on the dashboard. With 64,000 (the exe's maximum, 64 times the toughest stock truck) a truck never gets near the point where damage costs power or steering (`truck.lua` starts the damage effects at a factor of 0.7).

**Deep Fording moves the damage box.** The official guide says the damage sensation area "is also used to test water overflows". Moving the box 1 m above its old top means water has to rise far over the cab before the truck gets water damage or stalls. The same box is used for hits, so the cab also takes almost no hit damage. Example ZIL-130: Y 1.57 to 2.17 became 3.17 to 3.37.

**AWD: what "none" and missing mean.** `Wheel@Torque` is `default` (always driven), `full` (driven when AWD is switched on) or `none`. The 4x2 trucks (ZIL-130 B-130, ZAZ A-968m, UMZ) have no Torque on the front wheels, so missing also means "not driven". Trucks that already have permanent AWD or a permanent diff lock (`Always`) keep them.

| Truck | Front wheels | Diff lock |
|---|---|---|
| kamaz65115 (C-65115), kraz256 (C-256) | none -> full | kamaz65115: None -> Default |
| zil130 (B-130), zaz968m (A-968m) | missing -> full | None -> Default |
| chevrolet_bison_1978, ford_ltl9000, freightliner_fl120, gmc_dw950 (DLC) | none -> full | unchanged |
| umz6a (The Ridge) | missing -> full | unchanged (Always) |

**Grippy Wheels.** Most wheels take friction from the templates in `_templates/trucks.xml`; the mod writes both values on every wheel class instead of changing the shared template file.

| Stock template | Body / Substance stock | Mod |
|---|---|---|
| Offroad | 1.0 / 1.2 | 2.0 / 3.0 |
| Default | 1.25 / 0.75 | 2.0 / 2.5 |
| Highway | 1.5 / 0.5 | 2.25 / 2.5 |
| explicit Substance 1.6 / 1.8 | | 4.0 / 4.5 |

**Winch Anchors, not a longer winch.** There is no winch length or force attribute in any file; the exe treats the cable as a Havok rope constraint. What a file can change is where a winch can hook on. All trucks and trailers already have anchor points in the base game; seven plants did not: `stump_b`, `small_tree_a` to `small_tree_d`, `fir_small_b`, `pine_small_b`. Small trees can still be uprooted when pulled hard.

**Unlocked Trucks edits level files.** The exe's level loader reads, per truck placed on a map, a type name, a matrix, addons, a trailer, damage, fuel and an `isLocked` byte. The mod copies the six maps that have locked trucks (Coast, Flood, River, The Ridge, The Valley, Old-timers) and clears those bytes, nothing else (checked byte by byte). Challenges, the tutorial and the Proving Ground are left alone. It works for a new game or a restarted map; existing saves keep their own truck state. The rest of the level head is parsed too (format from `TerrainSTGSave.cpp` in the exe: `nDriveTruck`, then the locators `eType, xzOrg, xzDir, fWidth, fLength, strId` and a matrix for types 7-8, then the map frame); the law `test_no_locked_truck_on_any_map_after_the_mod` checks all 11 maps: no locked truck after the mod and nothing after the trucks changed. "Plains" has no locked truck in its file at all; what is locked there are garages (see below).

The 16.10 test: "nothing changed" on River, The Ridge, The Valley and Old-timers. What is certain: the files of these maps lock River - A-968m and C-65115, Ridge - a trailer, Valley - D-6317 and two trailers, Old-timers - 13 records; the mod clears them (law on every map), the package is mounted above `Media.zip` and the DLC archives, and the exe reads that byte (`TerrainSTGLoad.cpp,471`, record field +0xa0) and checks it when it places the trucks of a new game (0x14070b705). What a file does not change: the profile keeps its own list of unlocked trucks (`status.unlockedTrucks`, "Cant read chunk &status.unlockedTrucks[0]" in the exe) and a flag `status.isAllGaragesUnlocked`. Which trucks can be picked for the slots and which are open in the garage is the profile, not the map; no file mod opens it, that is a job for the profile tool (waiting for a yes). Open question for the tester: was it the lock of a truck standing on the map ("Approach the truck to unlock it") or the lock in the truck list of the slots / garage.

## Not possible as a normal mod

| Idea | Why | Options |
|---|---|---|
| No fog of war / map revealed | The fog (cloaking) map lives only in saves (`.sts`: `nCloakingWidth`, `cloakingData`) and in the profile (`UserProfile.stu`: the mini map). The level files have none. | Edit a save with the game closed (clear `cloakingData`); or drive to the watchpoints; a level-file trick (move a watchpoint locator next to the start and widen it) is untested and would trigger achievements, so it is not built |
| Longer and stronger winch | No attribute exists (see above) | Only an exe patch, which is out of scope |
| Zero fuel consumption | Not in the files (see above) | The big tank |
| Trucks unlocked for the start slots | Kept in the profile (`status.unlockedTrucks`) | Not touched; Unlocked Trucks covers the trucks on the maps |
| All garages open ("Plains" and the other maps) | A garage is a level locator of type 1 with no lock flag. The lock is game state: a garage needs 4 garage points (8 for multiplayer hardcore), coded in the exe; a new game gives them only to garages within 64 m of the drive truck, the others open when cargo that carries garage points is unloaded there. Both numbers are read back from the exe in the tests (`engine_limits.read_exe_garage_rules`) | A save or profile tool (waiting for a yes); moving garage locators next to the start would change the map, so it is not built |

## The real cause of the crashes (11.10): package names longer than 16 characters

Every in-game crash from the first test (03.10) to the sixth (10.10) is the same one: 18 Windows Error Reporting entries and 10 crash dumps (`%LOCALAPPDATA%\CrashDumps\MudRunner.exe.*.dmp`), all `MSVCR110.dll+0x6d5ff`, code `c0000409`, fast-fail code 5 (the C runtime's "invalid parameter"). The stack in every dump: `MudRunner.exe+0x7ef718` called `strncpy_s`, and the 17-byte buffer next to it holds the start of our package name ("penTrail_Infinit", "penTrail_No_Dama", "penTrail_Unlocke", "penTrail_Probe_I", ...).

What the exe does there (read from the machine code): for a truck (`classes/trucks/<name>.xml`) or a level (`levels/<name>.stg`) it asks PhysFS which archive the file came from (`PHYSFS_getRealDir`); if that is a `.zip`, it copies the archive name between the last `/` and the `.` with `strncpy_s(buf, 17, name, len)`, then compares it with the `%llx` id of every loaded Workshop item to find the mod the truck belongs to. Workshop zips are named after the item id (`47f38fe1.zip`, 8 characters), `Media` and `_dlc_oldtimers` fit as well. `OpenTrail_Infinite_Fuel` has 23 characters: `strncpy_s` finds the buffer too small and ends the game.

That explains every result: all packages with trucks or levels crashed, whatever was inside (even byte-identical stock files, 04.10); wheel, plant and strings packages never go through this function, so they worked with equally long names. The Zip64 headers, the engine limits and "stock truck files cannot be shadowed" were real findings or careful choices, but none of them was the crash.

The fix: package names of at most 16 characters before `.zip`, lowercase letters, digits and `_`, never only hex digits (that could look like a Workshop id): `opentrail_fuel.zip`, `opentrail_damage.zip`, ... and the probes `otprobe_<name>.zip`. `tools/engine_limits.py` holds the limit (`ARCHIVE_NAME_MAX = 16`) and reads it back from the exe; the build refuses a longer name; the law `tests/test_archive_names.py` checks every package name, also the files in `build\local`. `install_local.py` still removes the old `OpenTrail_*.zip` lines. **If you put the packages in Config.xml by hand, do not rename them.**

Not explained: on 10.10 at 11:57 `--probe truck` (then named `OpenTrail_Probe_Truck.zip`, 21 characters) left no crash report, although it holds a truck file. And the 10.10 report "Infinite Fuel works": the Config.xml backups show that Infinite Fuel was not installed at all that day before 23:06 (the game then ran with the wheel probe only).

## Your own set: several mods in one truck (16.10)

Double-click **"Собрать свой мод.bat"** in the repository root (or run `.venv\Scripts\python tools\combine.py`). It asks in Russian for mod numbers (for example `6 2 5` - Big Fuel Tank, Powerful Engines, No Damage), builds ONE package `build\custom\opentrail_custom.zip` (16 characters, the most the game takes) and offers to install it (game closed, a Config.xml backup is written). In game every truck gets one copy "<truck> (Custom)", in Russian "(Свой набор)", with all chosen changes. Wheels, winch anchors and unlocked map trucks go in as in their own packages. Undo: start the bat again and choose `0` (or `install_local.py --remove --apply`).

Without questions: `tools\combine.py --mods infinite_fuel,powerful_engines,no_damage --install`; `--list` lists the mods.

Laws (`tests/test_combine.py`): the copy is the sum of the parts (every value a chosen mod changes holds exactly what that mod gives alone, the rest is stock); mods that change the same value are never silently stacked: Powerful Engines and Hyper Power both set the torque and the gear speeds, so the script asks which one to keep, and with `--mods` it stops and names both (`build_mods.conflicts`). No other mods overlap. Install your own set alone: `install_local.py --custom --apply` installs only it.

## Open maps: profile edit (16.10)

Double click **`Открыть карты MudRunner.bat`** (game closed). Item `1` lists the maps short of points and asks yes/no; only then `%APPDATA%\SpinTires MudRunner\UserProfile.stu` is changed, a backup `UserProfile.stu.opentrail-<time>` is made next to it. Item `4` restores the newest backup. CLI: `tools/unlock_profile.py --maps [--write]`, `--restore --write`.

From the exe: a map's lock is a number in the code (`level_coast` 1, `level_river` 2, `level_hill` 2, `level_flood` 3, `level_dlc3_02` 1, others 0, `engine_limits.read_exe_map_requirements`), compared with `profile.numLogPoints`; a map with `status.nMinCompleteBalance` != 0 is open anyway. The tool raises `numLogPoints` to 3 (never lowers it); every other byte stays. The whole file format is parsed to the last byte (`tools/profile_stu.py`, from the STU loader 0x1407e3a00); no checksum, no encryption. Laws in `tests/test_profile.py` (temp copies only), 6 mutations.

Garages and trucks (items 2 and 3) are not done: a garage lock is garage points in the map save (`UserSaves/*.sts`); the profile's `status.unlockedTrucks` is a list of 12-byte truck positions (3 floats) per save. Neither is understood well enough to edit.

## Install (local packages)

The game reads extra files through `<MediaPath>` lines in its Config.xml. The first copy of a file wins, so the packages go above `Media.zip`.

1. Build (or take the zips from a release):
   ```
   uv venv .venv && uv pip install --python .venv\Scripts\python.exe -r tools\requirements.txt
   .venv\Scripts\python tools\build_mods.py
   ```
   The packages land in `build\local\`.
2. Close the game. Look at what would change, then write it:
   ```
   .venv\Scripts\python tools\install_local.py
   .venv\Scripts\python tools\install_local.py --apply
   .venv\Scripts\python tools\install_local.py --all --apply
   .venv\Scripts\python tools\install_local.py --mods no_damage,infinite_fuel --apply
   ```
   Without `--mods` it installs the safe set: every mod except the opt-in ones (`"opt_in"` in `mods/order.json`: Hyper Power, the alternative to Powerful Engines, and Unlocked Trucks, which replaces whole level files). `--all` adds them. The script prints which mods it installs and which it leaves out. It edits `%APPDATA%\SpinTires MudRunner\Config.xml` (the file the game saves on exit), removes older OpenTrail lines, inserts the new ones above `<MediaPath Path="Media.zip" />` in the load order below and keeps a backup `Config.xml.opentrail-<time>` next to it.

   By hand: add lines like `<MediaPath Path="D:/Games/OpenTrail/opentrail_damage.zip" />` above `<MediaPath Path="Media.zip" />`.
3. Start the game. The current game build no longer writes `%APPDATA%\SpinTires MudRunner\Log.txt` (it stays from January 2026 even after normal runs without mods, while the profile and Config.xml are rewritten), and a crash leaves no local dump (the exe hands crashes to `SteamAPI_WriteMiniDump`; `Steam\dumps` has nothing from MudRunner). So the check is in game, see below.
4. For Unlocked Trucks start a new game on the map.
5. To remove: `install_local.py --remove --apply`, or delete the lines.

Single player only: the exe compares hashes of the truck, wheel and template files for multiplayer.

### Check in game, one mod at a time

Close the game before every command (the game rewrites Config.xml on exit). Each command replaces the OpenTrail lines of the one before; `--remove --apply` takes them all out. Back up `%APPDATA%\SpinTires MudRunner\UserSaves` first if you care about the saves.

```
cd <repository>
.venv\Scripts\python tools\install_local.py --mods infinite_fuel --apply
    THE KEY CHECK: the same package that crashed on 10.10, now named opentrail_fuel.zip.
    Truck menu opens, "A-469 (Big Tank)" is in the list, the tank is 4x stock (A-469: 320 l), the truck drives off without jerking
.venv\Scripts\python tools\install_local.py --mods unlocked_trucks --apply
    "Single player" opens; new game on Flood or Coast: the trucks on the map are not locked
.venv\Scripts\python tools\install_local.py --probe truck --apply
    for the record: a stock uaz469.xml byte for byte under a short name. Truck menu opens = stock
    truck files CAN be shadowed (they were never the problem)
.venv\Scripts\python tools\install_local.py --mods no_damage --apply
    "A-469 (No Damage)": hits barely move the damage bar (64000)
.venv\Scripts\python tools\install_local.py --mods powerful_engines --apply
    "C-4310 (Powerful)": pulls much harder in mud and uphill
.venv\Scripts\python tools\install_local.py --mods hyper_power --apply
    "C-4310 (Hyper)": wheels spin easily, climbs almost anything
.venv\Scripts\python tools\install_local.py --mods awd_difflock --apply
    "B-130 (AWD)" or "C-65115 (AWD)": AWD and diff lock can be switched on
.venv\Scripts\python tools\install_local.py --mods deep_fording --apply
    "C-4310 (Deep Fording)": deep water, no water damage, the engine does not stall
.venv\Scripts\python tools\install_local.py --apply
    the safe set together (all but Hyper Power and Unlocked Trucks)
.venv\Scripts\python tools\install_local.py --remove --apply
    back to the plain game
```

Grippy Wheels, Winch Anchors and `--probe names` already worked on 10.10. If a check crashes, the crash dump in `%LOCALAPPDATA%\CrashDumps` (newest `MudRunner.exe.*.dmp`) tells why.

## What went wrong in the first test, and the zip law

**Corrected on 11.10:** the first test crashed for the package name too (the same crash signature as all later ones). The Zip64 problem below is real for PhysFS 2.0 and stays fixed, but it was not the crash.

The first in-game test of 1.0.0 (all nine packages) did not reach the main menu: the game went straight into a map and crashed on Esc. Without packages it worked. The cause, found without starting the game: the Unlocked Trucks zip. Python's streaming zip writer, called with `force_zip64=True`, wrote the six level files with Zip64 local headers ("version needed" 4.5, sizes 0xFFFFFFFF, a Zip64 extra field) while the central directory held the real sizes. MudRunner reads zips with PhysFS 2.0 (its messages "ZIP bigger than 2 gigs?!" and "Corrupted archive" are in the exe). That version has no Zip64 support and compares every local header with the central directory before it opens a file, so all six level files were "corrupted". The first archive that lists a path owns it, so the game did not fall back to Media.zip either.

`tools/zipcheck.py` checks these PhysFS 2.0 rules: no Zip64 anywhere, local header = central directory (version, method, CRC, sizes), deflate or store only, under 2 GB. Media.zip, the DLC archives, MeshCache.zip and all 8 Workshop items installed on this PC pass; the 1.0.0 level package failed with 24 problems. The build now runs the check on every package and stops on any problem, and the level files are written as plain zip 2.0 entries (size given up front). The class-file packages were always fine.

## Engine limits (second in-game test)

**Corrected on 11.10:** the second test crashed for the package name as well. The exe does clamp these values (and reports them), so the limits stay.

With the safe set the main menu opened, but the game crashed on "Single player", the screen that loads the trucks of the maps. The byte-level comparison of every shipped file with the stock one found nothing (same encoding, no BOM, same line ends, same elements, only the target attributes changed). The cause is in the exe: it reads some attributes through range-checked getters, clamps a value outside the range and reports it through its XML error logger ("| Clamping node %s value %d (maximum is %d)"). Three mods were outside:

| Attribute | Exe limit | 1.0.0 value | Now |
|---|---|---|---|
| TruckData FuelCapacity | max 64,000 (`cmp reg, 0xFA00`) | 100,000 (Infinite Fuel) | 64,000 |
| Damage Capacity | max 64,000 | 1,000,000 (No Damage) | 64,000 |
| Motor Torque | max 1,000,000 (float getter) | up to 2,400,000 (Hyper Power x10) | x10, capped at 1,000,000 |
| WheelFriction Substance / Body | 0.1 to 10.0 | up to 4.5 | unchanged |

`tools/engine_limits.py` holds the table and reads the same numbers back from the installed exe; the build stops on any value outside it, and the tests check every truck and wheel of every package, all packages together and the Workshop variants.

### Probe packages and the caches

`tools/build_probe.py` writes small probe packages, each mounted alone by `install_local.py --probe <name> --apply`:

| Probe | Content | In game |
|---|---|---|
| `manifest` | only a `<ModStrings>` file at the zip root, overrides nothing | works (10.10) |
| `names` | only `strings/<lang>/opentrail_probe.txt`, the way the truck mods name their trucks, overrides nothing | works (10.10) |
| `plant` | `classes/plants/stump_b.xml`, byte for byte | works |
| `wheel` | `classes/wheels/kamaz_offroad.xml`, byte for byte | works |
| `truck` | `classes/trucks/uaz469.xml`, byte for byte: **replaces a stock truck file, diagnosis only** | crashed only because of the long name; with the short name: 7th test |
| `identical` | the three stock files above | crashed 04.10 (long name) |
| `changed` | `uaz469.xml` with FuelCapacity 80 -> 81 | crashed 04.10 (long name) |

The probe zips are named `otprobe_<name>.zip` (at most 16 characters, see above).

The texture and mesh caches (`TextureCache.zip` as `_t/`, `MeshCache.zip` as `_m/`) are keyed by mesh and texture names (`_m/trucks_kamaz4310`); the exe falls back to `MeshCache/` and the source `meshes/` / `textures/` folders. Class XML files are not part of any cache, and the packages ship no mesh or texture, so a changed truck XML cannot make a cache entry stale. Workshop items ship their own `_m/` and `_t/` entries only because they bring new meshes.

## Tests 3 to 5 in game (conclusion corrected on 11.10)

**Corrected:** none of the crashes below came from the truck files. All of them are the package-name crash described above; the long names were the only thing the crashing packages had in common. What follows is the record of what we believed then.


Third test (04.10), single mods: Winch Anchors alone (plant files) and Grippy Wheels alone (wheel files) work; Infinite Fuel alone (truck files, only `FuelCapacity` changed, 64,000, within the limits) crashed on "Single player" and on Esc. Fourth test (09.10): thin heirs (`<_parent File="kamaz4310"/>` plus one value) crashed at the truck menu, and so did a byte-for-byte copy of a truck file in an extra package. Fifth test (10.10, commit b7bdd72): `--probe manifest`, `plant` and `wheel` work; `--probe truck` (one stock truck file, byte for byte) crashes when the truck menu opens; Infinite Fuel as full copies `otf_*` under their own names works, the truck in the slot drives.

So the game does not tolerate a stock `classes/trucks/*.xml` from an extra MediaPath, whatever its content. (A likely mechanism, found in the exe: saves and the profile store a checksum per truck, `dwTruckCRC`, and the truck menu and the saves are tied to the stock trucks.) The fix: every truck mod ships full copies under new names, with icon and names, the way Workshop items do. Two guards: the build stops if a package holds a stock truck file (a truck mod: any stock file), and the law test `tests/test_truck_law.py` checks every output on its own (packages in memory and as written, custom packages, the Workshop folders, the packages in `build\local`) against the stock truck list read straight from the game archives.

## Load order

Top to bottom (`mods/order.json`), the same order as the MediaPath lines:

1. Hyper Power (opt-in)
2. Powerful Engines
3. AWD and Diff Lock
4. Deep Fording
5. No Damage
6. Infinite Fuel
7. Grippy Wheels
8. Winch Anchors
9. Unlocked Trucks

Every truck mod adds its own trucks, so no two packages ship the same file (a test checks it) and the order matters only against other people's mods that replace the same wheel, plant or level files. Each truck mod gives one change per truck. For several changes on ONE truck build a custom package:

```
.venv\Scripts\python tools\build_mods.py --only infinite_fuel,no_damage,grippy_wheels
```

This writes `build\local\opentrail_custom.zip`: trucks `otc_<truck>` named "C-4310 (Custom)" plus the chosen wheel or plant changes. Hyper Power and Powerful Engines cannot go into one custom package. `tools/combine.py` does the same into `build\custom\` (see "Your own set").

## Steam Workshop

MudRunner Workshop items are uploaded with the MudRunner Editor, which renames every file on publish, so a Workshop item cannot replace stock files. The Workshop versions therefore add new trucks, the same full copies as the local packages (no `<_parent>`), with the stock selection icon and a name in `strings.xml` (`<ModStrings>`), like "C-65115 (AWD)". Players pick them in the truck slots at map start or spawn them in the Proving Ground. Only base-game trucks get variants: the game checks DLC ownership by asset name, and a renamed DLC truck could slip past that check. Winch Anchors and Unlocked Trucks change stock files only and have no Workshop version.

`.venv\Scripts\python tools\build_workshop.py` writes `workshop\NN_OpenTrail_<Name>\` (7 folders) and the release assets. How to upload: [WORKSHOP.md](WORKSHOP.md).

| Workshop item | Adds |
|---|---|
| OpenTrail Hyper Power, Powerful Engines, Deep Fording, No Damage, Infinite Fuel | 20 trucks each |
| OpenTrail AWD and Diff Lock | 5 trucks (the base-game trucks that lack AWD or a diff lock) |
| OpenTrail Grippy Wheels | 24 wheel types and 20 trucks that use them |

## How the build works

`tools/mrxml.py` parses the class files (a tolerant parser: several top-level elements, repeated attributes) and resolves them like the game: `<_parent>` inheritance with position-matched child nodes, `_inheritRemove`, `_noinherit`, `_template` and `<_templates Include="trucks">` (official modding guide, Appendix C).

A mod in `mods/<name>/mod.json` states the effective value every target must have, for example "Torque of every drivable truck = stock x2.5". The build resolves each class, edits the value in place when it comes from the same file, otherwise writes the attribute on the file's own node, then resolves again and stops on any mismatch. Parents are patched first, so a child that does not override a value inherits the patched one. The patched files differ from the stock ones only in the changed values.

## Tests

```
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python tools\mutation_check.py
```

- every one of the 36 drivable trucks (20 base, 16 DLC) and 50 wheel types has the mod's effective value, for each package alone and for all of them in the load order;
- every patched file parses; where the stock file is well-formed XML the patched one is too; the element structure is unchanged; only the targeted attributes change;
- no divisor-like value (fuel capacity, damage capacity, torque, gear speeds, friction, masses) is 0 or negative, and no mod writes a 0;
- no two packages ship the same file; Hyper Power is x10 capped at the engine limit; a custom package holds exactly the chosen mods;
- all 25 level files parse; unlocking changes exactly the `isLocked` bytes; streamed level copies are identical apart from them;
- the truck-file law (`tests/test_truck_law.py`): no mod writes to `classes/trucks/<stock name>.xml`, checked against the stock list from the game archives in every package (in memory and as written), in custom packages, in the Workshop folders and in `build\local`; every truck entry is `<prefix>_<drivable stock truck>.xml`; a truck mod ships no stock path at all; every new truck has a name in all 12 language folders (Russian suffix in `ru`), UTF-16 with CRLF like the game's files;
- the new trucks are full copies (no `<_parent>`) with the stock selection icon, and resolve to the stock truck with only the mod's values changed (no other attribute differs, no value becomes 0);
- the Workshop folders: only `.xml`, `.png` and the selection icons, lowercase unique names, no name that shadows a stock file, `strings.xml` names every class, 512x512 preview, CRLF copy-paste texts in English and Russian, base-game trucks only;
- the engine-limits law (`tools/engine_limits.py`): no value above what the exe accepts, and the table matches the exe;
- the zip law (`tools/zipcheck.py`): every package passes the PhysFS 2.0 rules; the stock archives and the Workshop items on this PC pass it too; a Zip64 zip fails it;
- the archive-name law (`tests/test_archive_names.py`): every package and probe name has at most 16 characters before `.zip` (the limit read back from the exe), only `a-z0-9_`, not only hex digits; the build refuses a longer name; the packages in `build\local` too; old `OpenTrail_*` lines are still removed;
- the Config.xml editor on a copy: the default is the safe set without opt-in mods and says so; `--help` and the output mark the probes that replace a stock truck file; no personal data in any tracked file, package or Workshop file;
- parser laws over generated XML (hypothesis, 400 examples; `HYPOTHESIS_PROFILE=thorough` for 4000).

`tools/mutation_check.py` breaks the product in 38 places in a temp copy (wrong values, wrong lock byte, LF instead of CRLF, a planted e-mail, broken inheritance merge, a truck mod that writes stock truck files with the build's guard switched off, copies named like the stock trucks, names missing in a language, the probe warning gone from `--help`, a 23-character package name with the build's name check switched off, a wrong name limit, ...) and checks that the named test fails each time.

## Files

| Path | What |
|---|---|
| `mods/<name>/mod.json` | The mod: ops, version, Workshop texts |
| `mods/order.json` | Load order and `replaces` |
| `tools/mrxml.py` | Parser, resolver, text edits |
| `tools/build_mods.py` | Local packages |
| `tools/build_workshop.py` | Workshop folders and release assets |
| `tools/install_local.py` | Config.xml lines (safe set by default) |
| `tools/zipcheck.py` | Can the game's PhysFS 2.0 read a zip |
| `tools/engine_limits.py` | Value limits the exe enforces |
| `tools/build_probe.py` | Probe packages (`--probe truck` crashes the game on purpose: diagnosis only) |
| `tools/mutation_check.py` | Mutation check |
| `tools/publish_github.sh` | Copy to GitHub without personal data (run only after the in-game test) |
| `docs/research.md` | How MudRunner mods work, with sources |
| `docs/release-notes/` | Release notes |

License: MIT.
