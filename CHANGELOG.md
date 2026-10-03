# Changelog

## 1.0.0 - not released yet (waiting for the in-game test)

First version, built from the files of MudRunner 0.6.8 with all four DLC.

Mods (public names "OpenTrail ..."):
- **Hyper Power**: Motor Torque x10, capped at 1,000,000, on 36 trucks. Replaces Powerful Engines.
- **Powerful Engines**: Motor Torque x2.5.
- **AWD and Diff Lock**: wheels with Torque none or missing get full on 10 trucks; DiffLockType None becomes Default.
- **Deep Fording**: the damage sensation box moved 1 m above its old top.
- **No Damage**: Damage Capacity 64,000 (the exe's maximum).
- **Infinite Fuel**: FuelCapacity 64,000 l, the exe's maximum (consumption is not in the files).
- **Grippy Wheels**: SubstanceFriction x2.5 (at least 2.5), BodyFriction x1.5 (at least 2.0) on 50 wheel types.
- **Winch Anchors**: winch sockets on 7 stumps and small trees.
- **Unlocked Trucks**: isLocked cleared for 24 trucks and trailers on 6 maps.
- Not possible as a file mod: fog of war (saves and profile only), winch length and force, fuel consumption.

Fixed after the first in-game test (the game skipped the main menu and crashed on Esc): the Unlocked Trucks zip had Zip64 local headers that the game's PhysFS 2.0 rejects. Level files are now plain zip 2.0 entries; `tools/zipcheck.py` checks every package; `install_local.py` installs the safe set (without Unlocked Trucks) unless `--all` or `--mods` is given, and prints the list.

Fixed after the second in-game test (the game crashed on "Single player"): FuelCapacity 100,000 and Damage Capacity 1,000,000 were over the exe's limit of 64,000, Hyper Power torque over 1,000,000; the exe clamps such values and reports them through its XML error logger. `tools/engine_limits.py` holds the limits (read back from the exe in the tests) and the build stops on any value outside. Hyper Power is opt-in in `install_local.py` too.

Fixed after the third in-game test (single mods: plants and wheels work, truck files crash "Single player" and Esc): the six truck mods ship heir classes (`otf_kamaz4310` inherits `kamaz4310`) instead of replacing stock truck files; the build refuses a package that replaces one. Probe packages (`tools/build_probe.py`, `install_local.py --probe [changed]`).

Tools: tolerant class XML parser and inheritance resolver, local packages for Config.xml MediaPath, custom packages (`--only`), Workshop folders for the MudRunner Editor (inherited base-game trucks), Config.xml installer with backup, test suite and mutation check.
