"""MudRunner map save UserSaves/<name>.sts: the truck lock bytes and the garage points.

Read from MudRunner.exe 0.6.8, the STS loader 0x14072c1a0 (GameSTSLoad.cpp, field names
from its "Cant read ..." strings). Only what the unlock tool edits is located; everything
else (truck physics state, mud, fog of war, logs) stays byte for byte as it is.

  u32 nFileVersion                    only 0x133efb9 (the current one) is edited here
  u32 numMods x { u64 nId, str strTitle }, u8, f32 fDayTime, u8 nVariant, u8 nNextVariant,
  f32 fVariantParam, stats (3 x f32, u32), achievements block (DialogAchievements.cpp 911..)
  u32 numTrucks, then per truck (GameSTSLoad.cpp 259-314):
      str desc.strType
      u32 numAddons x { str name, str strParentFrame, 4x4 f32 tmAddon,
                        u32 numExtraParents x str, u32, u32 }
      u32, u32, u32                   (fuel, damage, repairs)
      4x4 f32 tmTruck
      f32 fDistanceTraveled, f32 fSteer
      u8  isUnlocked                  0x14072cf85: not 0 -> UnlockTruck (0x1406cbcf0)
      u32 dwTruckCRC
      ... the truck's physics state (variable length) ...
  ... fog of war (nCloakingWidth, nCloakingHeight, data) ...
  u32 numGarages x { f32x2 xzOrg, u32 numGaragePoints }   (GameSTSLoad.cpp 473-478)
      the loader gives the points to the level's type-1 locators within 1 m of xzOrg
      (AddGaragePoints 0x1406ccb00); a garage is open at engine_limits.GARAGE_NEED points.

str = u16 length (with the closing zero byte) + that many bytes.

The truck records are found by their header (a name, the add-ons and two orthonormal
4x4 matrices) and must be exactly numTrucks, the first right after the count; the garage
block is found by the level's own garage positions (levels/<level>.stg, locators of type 1),
float for float. Anything else is refused (StsError) and nothing is changed.

Why this file and not the level files: the locked trucks a new game puts on the map are not
in levels/*.stg at all (engine_limits.RANDOM_TRUCK_POOL); the exe spawns them locked, and
the save keeps their isUnlocked byte.
"""
import re
import struct

VERSION = 0x133efb9
MAX_NAME = 256
MAX_ADDONS = 64
MAX_EXTRA = 16


class StsError(ValueError):
    pass


class _Bad(Exception):
    pass


def _str(d, o):
    if o + 2 > len(d):
        raise _Bad()
    n = struct.unpack_from("<H", d, o)[0]
    if n == 0 or n > MAX_NAME or o + 2 + n > len(d) or d[o + 1 + n] != 0:
        raise _Bad()
    s = d[o + 2:o + 1 + n]
    if not all(32 <= c < 127 for c in s):
        raise _Bad()
    return s.decode("ascii"), o + 2 + n


def _matrix(d, o):
    if o + 64 > len(d):
        raise _Bad()
    f = struct.unpack_from("<16f", d, o)
    if f[3] != 0 or f[7] != 0 or f[11] != 0 or f[15] != 1.0:
        raise _Bad()
    for r in range(3):
        if abs(f[4 * r] ** 2 + f[4 * r + 1] ** 2 + f[4 * r + 2] ** 2 - 1) > 1e-3:
            raise _Bad()
    if not all(abs(v) < 5000 for v in f[12:15]):
        raise _Bad()
    return f


def _truck_at(d, o):
    start = o
    typ, o = _str(d, o)
    if o + 4 > len(d):
        raise _Bad()
    na = struct.unpack_from("<I", d, o)[0]
    o += 4
    if na > MAX_ADDONS:
        raise _Bad()
    addons = []
    for _ in range(na):
        name, o = _str(d, o)
        _frame, o = _str(d, o)
        _matrix(d, o)
        o += 64
        if o + 4 > len(d):
            raise _Bad()
        ne = struct.unpack_from("<I", d, o)[0]
        o += 4
        if ne > MAX_EXTRA:
            raise _Bad()
        for _ in range(ne):
            _e, o = _str(d, o)
        o += 8
        addons.append(name)
    o += 12
    tm = _matrix(d, o)
    o += 64 + 8
    if o + 5 > len(d) or d[o] not in (0, 1):
        raise _Bad()
    return dict(start=start, type=typ, addons=addons, x=tm[12], y=tm[13], z=tm[14],
                unlocked=d[o], unlocked_at=o, end=o + 5)


def _check_version(d):
    if len(d) < 8:
        raise StsError("file too short")
    v = struct.unpack_from("<I", d, 0)[0]
    if v != VERSION:
        raise StsError("save version 0x%x is not the one this tool knows (0x%x)" % (v, VERSION))


def trucks(data):
    """The truck headers of a save: [dict(start, type, addons, x, y, z, unlocked, unlocked_at)].
    Raises StsError when they cannot be found exactly."""
    d = bytes(data)
    _check_version(d)
    found = []
    for m in re.finditer(rb"[\x02-\xff]\x00[A-Za-z0-9_]", d):
        if found and m.start() < found[-1]["end"]:
            continue
        try:
            found.append(_truck_at(d, m.start()))
        except (_Bad, struct.error):
            pass
    if not found:
        raise StsError("no truck found")
    at = found[0]["start"] - 4
    count = struct.unpack_from("<I", d, at)[0]
    if count != len(found):
        raise StsError("numTrucks is %d, found %d truck headers" % (count, len(found)))
    return found


def unlock_trucks(data):
    """(copy of data with isUnlocked = 1 on every truck, the trucks that were locked)."""
    ts = trucks(data)
    b = bytearray(data)
    locked = [t for t in ts if not t["unlocked"]]
    for t in locked:
        b[t["unlocked_at"]] = 1
    return bytes(b), locked


def garages(data, garage_xz):
    """[dict(x, z, points, points_at)] of the save, in the order of garage_xz (the level's
    garage locators). [] when the level has none. Raises StsError unless the block with
    exactly these positions is found once."""
    d = bytes(data)
    _check_version(d)
    if not garage_xz:
        return []
    head = struct.pack("<I", len(garage_xz)) + struct.pack("<ff", *garage_xz[0])
    hits = []
    for m in re.finditer(re.escape(head), d):
        o = m.start() + 4
        out = []
        for x, z in garage_xz:
            if o + 12 > len(d) or d[o:o + 8] != struct.pack("<ff", x, z):
                break
            out.append(dict(x=x, z=z, points=struct.unpack_from("<I", d, o + 8)[0], points_at=o + 8))
            o += 12
        if len(out) == len(garage_xz):
            hits.append(out)
    if len(hits) != 1:
        raise StsError("garage block found %d times" % len(hits))
    if any(g["points"] > 64 for g in hits[0]):
        raise StsError("implausible garage points")
    return hits[0]


def open_garages(data, garage_xz, need):
    """(copy of data with every garage at >= need points, the garages that were below)."""
    gs = garages(data, garage_xz)
    b = bytearray(data)
    low = [g for g in gs if g["points"] < need]
    for g in low:
        struct.pack_into("<I", b, g["points_at"], need)
    return bytes(b), low


def changed_offsets(a, b):
    """Byte offsets where a and b differ (same length required)."""
    if len(a) != len(b):
        raise StsError("length changed")
    return [i for i in range(len(a)) if a[i] != b[i]]
