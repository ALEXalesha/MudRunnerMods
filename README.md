# MudRunnerMods

OpenTrail: gameplay mods for Spintires: MudRunner, built from the game's own files, plus the tools that build and check them.

> Not affiliated with or endorsed by Saber Interactive or Focus Entertainment. "Spintires: MudRunner" is their trademark. The mods are fan-made and for single player.

[Русская версия](README.ru.md)

The repository holds no game files. `tools/build_mods.py` reads the class XML from the installed game (`Media.zip` and the four DLC archives), changes only what a mod needs and writes one override package per mod. After a game update, run the build again.

## The mods

Ten ideas, nine mods. The fog of war cannot be removed with game files (see "Not possible").

**The six truck mods add NEW trucks and never touch a stock truck file.** Each changed truck is a full copy of the stock one under its own name, `<prefix>_<stock name>` (for example `otf_kamaz4310`), with the stock selection icon and its own display name, "C-4310 (Infinite Fuel)" (in Russian "C-4310 (Бесконечное топливо)"). The game does not accept a stock `classes/trucks/*.xml` from an extra package: in-game tests 3 to 5 crashed on "Single player", on Esc or at the truck menu, even with a byte-for-byte copy (`--probe truck`), while the new trucks of Infinite Fuel worked (10.10). Pick the new trucks in the truck slots when you start a map, or spawn them in the Proving Ground; the trucks placed on the maps stay stock. Grippy Wheels, Winch Anchors and Unlocked Trucks replace stock wheel, plant and level files (wheels and plants were tested in game and work).

| Mod | New trucks | Name in the game (English / Russian) |
|---|---|---|
| Hyper Power | `oth_<truck>`, 36 | "C-4310 (Hyper)" / "C-4310 (Гипермощь)" |
| Powerful Engines | `otp_<truck>`, 36 | "C-4310 (Powerful)" / "C-4310 (Мощный мотор)" |
| AWD and Diff Lock | `ota_<truck>`, 10 (the trucks that lack AWD or a switchable diff lock) | "B-130 (AWD)" / "B-130 (Полный привод)" |
| Deep Fording | `otw_<truck>`, 36 | "C-4310 (Deep Fording)" / "C-4310 (Глубокий брод)" |
| No Damage | `otd_<truck>`, 36 | "C-4310 (No Damage)" / "C-4310 (Без поломок)" |
| Infinite Fuel | `otf_<truck>`, 36 | "C-4310 (Infinite Fuel)" / "C-4310 (Бесконечное топливо)" |
| custom package (`build_mods.py --only`) | `otc_<truck>`: all chosen truck changes on one truck | "C-4310 (Infinite Fuel + No Damage)" |

36 = every drivable truck, 20 of the base game and 16 of the DLC. Names: the game reads `<ModStrings>` only for Steam Workshop items (the exe opens `<item id>.xml`), so a local package carries a new strings file per language, `strings/<lang>/opentrail_<mod>.txt`, in the format of the game's own `assets.txt` (UTF-16, `/key` line, name line). The game lists `strings/<lang>/*.txt` itself (`china.txt` exists in two languages only and its name is not in the exe), so no stock strings file is replaced. If the game refuses such a file (`install_local.py --probe names` tells), `build_mods.py --no-names` builds the packages without names.

| Mod (package) | What it changes | Covers |
|---|---|---|
| Hyper Power (`OpenTrail_Hyper_Power.zip`) | `Motor@Torque` x10, capped at 1,000,000 (the game's limit). For fun. Replaces Powerful Engines; opt-in | 36 drivable trucks, base + DLC |
| Powerful Engines (`OpenTrail_Powerful_Engines.zip`) | `Motor@Torque` x2.5 (stock 16,000 to 240,000) | 36 trucks |
| AWD and Diff Lock (`OpenTrail_AWD_and_Diff_Lock.zip`) | Wheels with `Torque="none"` or no Torque get `full`; `DiffLockType="None"` becomes `Default` (switchable) | 10 trucks without AWD or a switchable diff lock |
| Deep Fording (`OpenTrail_Deep_Fording.zip`) | `Damage@SensationMin/Max` box moved 1 m above its old top (0.2 m tall) | 36 trucks |
| No Damage (`OpenTrail_No_Damage.zip`) | `Damage@Capacity` 64,000, the game's maximum (stock 160 to 1000) | 36 trucks |
| Infinite Fuel (`OpenTrail_Infinite_Fuel.zip`) | `TruckData@FuelCapacity` 64,000 l, the game's maximum (stock 40 to 800) | 36 trucks |
| Grippy Wheels (`OpenTrail_Grippy_Wheels.zip`) | `WheelFriction@SubstanceFriction` x2.5, at least 2.5; `@BodyFriction` x1.5, at least 2.0 | 50 wheel types |
| Winch Anchors (`OpenTrail_Winch_Anchors.zip`) | `GameData/WinchSocket` on 7 stumps and small trees that had none | 7 plant classes |
| Unlocked Trucks (`OpenTrail_Unlocked_Trucks.zip`, 295 MB) | `isLocked` cleared in the truck records of the level files | 24 trucks and trailers on 6 maps |

### Why some mods work the way they do

**Infinite Fuel is a big tank, not zero consumption.** No truck file and no attribute name in the exe sets fuel consumption; the game computes it in code (the UI only prints `%d L / Min`). A 64,000 l tank is the closest thing a file can do: the exe clamps FuelCapacity at 64,000 (see "Engine limits"). At 20 l/min it lasts more than 50 hours of driving. Starting fuel on the maps is a percentage (the level files store `fFuel` as 0 to 100), so trucks start full. Addon tanks and cisterns are not changed.

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

**Unlocked Trucks edits level files.** The exe's level loader reads, per truck placed on a map, a type name, a matrix, addons, a trailer, damage, fuel and an `isLocked` byte. The mod copies the six maps that have locked trucks (Coast, Flood, River, The Ridge, The Valley, Old-timers) and clears those bytes, nothing else (checked byte by byte). Challenges, the tutorial and the Proving Ground are left alone. It works for a new game or a restarted map; existing saves keep their own truck state.

## Not possible as a normal mod

| Idea | Why | Options |
|---|---|---|
| No fog of war / map revealed | The fog (cloaking) map lives only in saves (`.sts`: `nCloakingWidth`, `cloakingData`) and in the profile (`UserProfile.stu`: the mini map). The level files have none. | Edit a save with the game closed (clear `cloakingData`); or drive to the watchpoints; a level-file trick (move a watchpoint locator next to the start and widen it) is untested and would trigger achievements, so it is not built |
| Longer and stronger winch | No attribute exists (see above) | Only an exe patch, which is out of scope |
| Zero fuel consumption | Not in the files (see above) | The big tank |
| Trucks unlocked for the start slots | Kept in the profile (`status.unlockedTrucks`) | Not touched; Unlocked Trucks covers the trucks on the maps |

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

   By hand: add lines like `<MediaPath Path="D:/Games/OpenTrail/OpenTrail_No_Damage.zip" />` above `<MediaPath Path="Media.zip" />`.
3. Start the game. The current game build no longer writes `%APPDATA%\SpinTires MudRunner\Log.txt` (it stays from January 2026 even after normal runs without mods, while the profile and Config.xml are rewritten), and a crash leaves no local dump (the exe hands crashes to `SteamAPI_WriteMiniDump`; `Steam\dumps` has nothing from MudRunner). So the check is in game, see below.
4. For Unlocked Trucks start a new game on the map.
5. To remove: `install_local.py --remove --apply`, or delete the lines.

Single player only: the exe compares hashes of the truck, wheel and template files for multiplayer.

### Check in game, one mod at a time

Close the game before every command (the game rewrites Config.xml on exit). Each command replaces the OpenTrail lines of the one before; `--remove --apply` takes them all out. Back up `%APPDATA%\SpinTires MudRunner\UserSaves` first if you care about the saves.

```
cd <repository>
.venv\Scripts\python tools\install_local.py --probe names --apply
    game: main menu, "Single player", the truck menu open as usual (only new strings files, nothing replaced)
.venv\Scripts\python tools\install_local.py --mods infinite_fuel --apply
    truck slot or Proving Ground: "A-469 (Infinite Fuel)"; the tank shows 64000 l
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
.venv\Scripts\python tools\install_local.py --mods grippy_wheels --apply
    any stock truck: much better grip in mud
.venv\Scripts\python tools\install_local.py --mods strong_winch --apply
    winch to a small stump or a small tree
.venv\Scripts\python tools\install_local.py --mods unlocked_trucks --apply
    new game on Flood or Coast: the trucks on the map are not locked
.venv\Scripts\python tools\install_local.py --apply
    the safe set together (all but Hyper Power and Unlocked Trucks)
.venv\Scripts\python tools\install_local.py --remove --apply
    back to the plain game
```

## What went wrong in the first test, and the zip law

The first in-game test of 1.0.0 (all nine packages) did not reach the main menu: the game went straight into a map and crashed on Esc. Without packages it worked. The cause, found without starting the game: the Unlocked Trucks zip. Python's streaming zip writer, called with `force_zip64=True`, wrote the six level files with Zip64 local headers ("version needed" 4.5, sizes 0xFFFFFFFF, a Zip64 extra field) while the central directory held the real sizes. MudRunner reads zips with PhysFS 2.0 (its messages "ZIP bigger than 2 gigs?!" and "Corrupted archive" are in the exe). That version has no Zip64 support and compares every local header with the central directory before it opens a file, so all six level files were "corrupted". The first archive that lists a path owns it, so the game did not fall back to Media.zip either.

`tools/zipcheck.py` checks these PhysFS 2.0 rules: no Zip64 anywhere, local header = central directory (version, method, CRC, sizes), deflate or store only, under 2 GB. Media.zip, the DLC archives, MeshCache.zip and all 8 Workshop items installed on this PC pass; the 1.0.0 level package failed with 24 problems. The build now runs the check on every package and stops on any problem, and the level files are written as plain zip 2.0 entries (size given up front). The class-file packages were always fine.

## Engine limits (second in-game test)

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
| `names` | only `strings/<lang>/opentrail_probe.txt`, the way the truck mods name their trucks, overrides nothing | to check (6th test) |
| `plant` | `classes/plants/stump_b.xml`, byte for byte | works |
| `wheel` | `classes/wheels/kamaz_offroad.xml`, byte for byte | works |
| `truck` | `classes/trucks/uaz469.xml`, byte for byte | **deliberately crashes the game, only for diagnosis** (truck menu, 10.10) |
| `identical` | the three stock files above | crashes too (holds `uaz469.xml`), diagnosis only |
| `changed` | `uaz469.xml` with FuelCapacity 80 -> 81 | crashes too, diagnosis only |

The texture and mesh caches (`TextureCache.zip` as `_t/`, `MeshCache.zip` as `_m/`) are keyed by mesh and texture names (`_m/trucks_kamaz4310`); the exe falls back to `MeshCache/` and the source `meshes/` / `textures/` folders. Class XML files are not part of any cache, and the packages ship no mesh or texture, so a changed truck XML cannot make a cache entry stale. Workshop items ship their own `_m/` and `_t/` entries only because they bring new meshes.

## Tests 3 to 5 in game: stock truck files cannot be shadowed

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

This writes `build\local\OpenTrail_Custom.zip`: trucks `otc_<truck>` named "C-4310 (Infinite Fuel + No Damage)" plus the chosen wheel or plant changes. Hyper Power and Powerful Engines cannot go into one custom package.

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
- the Config.xml editor on a copy: the default is the safe set without opt-in mods and says so; `--help` and the output mark the crashing probes; no personal data in any tracked file, package or Workshop file;
- parser laws over generated XML (hypothesis, 400 examples; `HYPOTHESIS_PROFILE=thorough` for 4000).

`tools/mutation_check.py` breaks the product in 34 places in a temp copy (wrong values, wrong lock byte, LF instead of CRLF, a planted e-mail, broken inheritance merge, a truck mod that writes stock truck files with the build's guard switched off, copies named like the stock trucks, names missing in a language, the crash warning gone from `--help`, ...) and checks that the named test fails each time.

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
