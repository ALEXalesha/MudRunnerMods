# Changelog

## 1.0.0 - not released yet (waiting for the in-game test)

First version, built from the files of MudRunner 0.6.8 with all four DLC.

Mods (public names "OpenTrail ..."):
- **Hyper Power**: Motor Torque x10 on 36 trucks. Replaces Powerful Engines.
- **Powerful Engines**: Motor Torque x2.5.
- **AWD and Diff Lock**: wheels with Torque none or missing get full on 10 trucks; DiffLockType None becomes Default.
- **Deep Fording**: the damage sensation box moved 1 m above its old top.
- **No Damage**: Damage Capacity 1,000,000.
- **Infinite Fuel**: FuelCapacity 100,000 l (consumption is not in the files).
- **Grippy Wheels**: SubstanceFriction x2.5 (at least 2.5), BodyFriction x1.5 (at least 2.0) on 50 wheel types.
- **Winch Anchors**: winch sockets on 7 stumps and small trees.
- **Unlocked Trucks**: isLocked cleared for 24 trucks and trailers on 6 maps.
- Not possible as a file mod: fog of war (saves and profile only), winch length and force, fuel consumption.

Tools: tolerant class XML parser and inheritance resolver, local packages for Config.xml MediaPath, custom packages (`--only`), Workshop folders for the MudRunner Editor (inherited base-game trucks), Config.xml installer with backup, test suite and mutation check.
