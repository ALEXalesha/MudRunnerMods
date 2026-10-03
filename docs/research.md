# How MudRunner mods work: findings and sources

Notes behind the design of these mods. "Exe" below means strings read from
`MudRunner.exe` 0.6.8 (read only, the game was never started); "files" means the
stock files in `Media.zip` and the DLC archives.

## Sources

| # | Source | What it gives |
|---|---|---|
| 1 | Focus Home, *Spintires: MudRunner modding guide (Beta)*, 21 February 2018, http://cdn.focus-home.com/admin/games/spintires_mudrunner/docs/ModdingGuide_Mudrunner.pdf | The official guide: the Editor, `_mods/<mod id>`, publishing, `strings.xml`, `preview.png`, XML inheritance (Appendix C), the damage sensation area |
| 2 | *The Big Book of MudRunner Map Making*, Steam guide https://steamcommunity.com/sharedfiles/filedetails/?id=1583079240 (mirror: https://www.mudrunnermods.com/spintires-mudrunner-map-making-big-book/) | Testing a mod through a `<MediaPath>` line in Config.xml with an absolute path; the game reads plain folders as well as zips; `preview.png` and `preview_wide.png`; publish warnings |
| 3 | mudrunnermods.com, *Files for installing mods*, https://www.mudrunnermods.com/files-installing-mods/, and the Steam thread https://steamcommunity.com/app/675010/discussions/0/1759104257584387382/ | A `<MediaPath Path="Media" />` line placed before `Media.zip` overrides stock files |
| 4 | Steam thread *The winch needs an extra 50% on its radius*, https://steamcommunity.com/app/675010/discussions/0/1726450077638514043/ | Winch length is not configurable in the vanilla game |
| 5 | Downloaded Workshop items on this PC (`steamapps/workshop/content/675010/*/*.zip`) | The published format: one zip per item, every file renamed after the item id, stock files only referenced |
| 6 | The game's own files and `Log.txt` | Everything in "Findings from the game files" below |

## Loading and load order

- The game mounts every `<MediaPath>` of Config.xml (zip or folder). Exe: the
  element takes `Path`, `DoPrepend`, `MountPoint` and `IncludeDLC`. Log.txt
  confirms each one: `MediaPath 'Media.zip' added.`
- The first mounted copy of a file wins, so override packages go ABOVE
  `<MediaPath Path="Media.zip" />` (source 3). Among our packages the upper line
  wins. `DoPrepend="true"` puts a path in front of everything (the texture and
  mesh caches use it), but several prepended lines end up in reverse order, so
  the install script uses plain lines above Media.zip instead.
- Absolute paths work (source 2 uses
  `c:/Program Files (x86)/.../Media/_mods/5e5c745c`).
- The game saves its config on exit to `%APPDATA%\SpinTires MudRunner\Config.xml`
  (Log.txt: `Combine config saved to ...`). That file has the `WorkingDirectory`
  attribute and is the one to edit, with the game closed.
- The DLC archives hold only new files: no path is in two archives (checked for
  all 1135 files).
- Archive reader: PhysFS 2.0 (exe messages "ZIP bigger than 2 gigs?!",
  "Corrupted archive", "buffer must fit in 32-bits"). No Zip64; a file opens only
  if its local header matches the central directory. The first archive that
  lists a path owns it, there is no fallback to a later archive.
  `tools/zipcheck.py` checks this; all stock archives and the Workshop items on
  this PC pass.
- Logs: the exe still names `Log.txt`, but the current build did not write it in
  any run since January 2026 (with or without mods). Crashes go to
  `SteamAPI_WriteMiniDump`; no MudRunner dump in `Steam\dumps`.
- Caches: `_m/<mesh>` and `_t/<texture>` entries, keyed by mesh/texture name;
  fallbacks `MeshCache/`, `TextureCache/` and the sources `meshes/`, `textures/`
  ("Texture %s out of date", "Out of date cache %s updated"). Class XML is not
  cached.
- Value limits: some attributes are read through range-checked getters that clamp
  and report via the XML error logger: FuelCapacity and Damage/Capacity at most
  64000, Motor Torque at most 1000000, wheel frictions 0.1 to 10.0
  (`tools/engine_limits.py`, read back from the exe).
- Multiplayer: the exe hashes `classes/trucks/`, `classes/wheels/`,
  `_templates/`, `media.xml` and levels and shows `game_game_version_modified`.
  Override packages are for single player.

## Steam Workshop

- Uploader: the MudRunner Editor (Steam > Library > Tools). File View > `_mods` >
  right click > Create new mod creates `Media\_mods\<id>` (8 to 16 lowercase
  letters and digits, the Workshop item id). Right click the mod > Publish opens
  the dialog: Title, Description, Visibility (Private by default), Preview
  (Autogenerate writes `preview.png` and `preview_wide.png`), change note. The
  first upload asks to accept the Workshop terms (sources 1, 2).
- On publish "those files would be automatically converted to game-friendly
  formats, renamed and packed" (source 1). Downloaded items confirm it:
  `classes/trucks/1v37v3em.xml`, a `<id>.xml` with `<ModStrings>`, and stock files
  only referenced (`<_parent File="load_logs_short" />`). A Workshop mod can add
  trucks, wheels and maps but cannot replace a stock file.
- Names: "file names within particular file groups (trucks, textures, level)
  must be unique! The game ignores folders" (source 1).
- `strings.xml` in the mod root names trucks and addons; "Mod localization is not
  currently supported so it's recommended to use English for all titles"
  (source 1).
- Files with unrecognized extensions give warnings and are left out (source 2).
- The preview can only be changed by publishing again (source 2).
- Unpublished mods can be tested in the Proving Ground (source 1).

## Findings from the game files

### Truck XML (`classes/trucks`, 144 files: 73 base, 71 DLC; 36 drivable trucks)

| Setting | Where | Notes |
|---|---|---|
| Fuel tank | `Truck/TruckData@FuelCapacity` (40 to 800) | No fuel consumption attribute exists in any file or in the exe's attribute names; consumption is computed in code (UI: `%d L / Min`) |
| Damage | `Truck/TruckData/Damage@Capacity` (160 to 1000) | UI `Damage: %d/%d`; the exe divides damage by capacity (damage factor, see truck.lua `truckInput.damageFactor`) |
| Damage area | `Damage@SensationMin`, `@SensationMax` | "This area is also used to test water overflows" (source 1); UI strings `water_level_warning`, `water_level_damage` |
| Engine | `Truck/TruckData/Motor@Torque` (16,000 to 240,000) | Gears in `Motor/Gear@AngVel` |
| Wheel drive | `Wheels/Wheel@Torque`: `default` always driven, `full` driven when AWD is on, `none` never | Exe: "Unrecognized wheel torque type"; missing = not driven (the front wheels of the 4x2 ZIL-130, ZAZ and UMZ have no Torque) |
| Diff lock | `TruckData@DiffLockType`: `None`, `Always`, missing or `Default` = switchable | Exe strings in parse order: `DiffLockType`, `None`, ..., `Default`, "Unrecognized diff lock type"; UI `difflock_none` = N/A, `difflock_always` = ALWAYS |
| Winch | `GameData/WinchSocket@Pos`, `@ParentFrame` | No length or force attribute anywhere; the rope is a Havok constraint (`ropeLength` is internal) |

Six stock files repeat an attribute (`zil_cistern.xml`: ImpactType twice;
`ford_f150.xml`: IsLight twice), and every class file has several top-level
elements, so `xml.etree` cannot read them; `tools/mrxml.py` is a tolerant parser.

### Wheels (`classes/wheels`, 50 files: 24 base, 26 DLC)

`WheelFriction@BodyFriction` (hard ground) and `@SubstanceFriction` (mud, water).
Most wheels take them from the templates in `_templates/trucks.xml`:
Offroad 1.0 / 1.2, Default 1.25 / 0.75, Highway 1.5 / 0.5.

### Levels (`levels/*.stg`, binary)

The exe's loader `TerrainSTGLoad.cpp` reads, in this order: u32 file version
(0x0133ED03), u32 GUID, u32 number of trucks, then per truck: string type,
4x4 matrix, addon list, string trailer, f32 damage, f32 fuel (percent),
u8 `isLocked`. Strings are u16 length + bytes with a trailing zero. All 25
levels parse with this layout. The locked trucks on the maps are these records
with `isLocked = 1`.

### Fog of war (cloaking)

`nCloakingWidth`, `nCloakingHeight` and `cloakingData` are read only from saves
(`.sts`, buffer reads next to the save code) and `nMiniCloakingWidth/Height`
from the profile (`UserProfile.stu`). The level loader has no cloaking data. So
a map revealed from the start is only possible by editing saves or the profile.

### Truck unlocks in the profile

`status.unlockedTrucks` and `status.startupTrucks` are read from the profile
(which trucks may be picked for the start slots). Not touched.
