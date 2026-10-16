"""Value limits that MudRunner.exe enforces when it reads class XML.

The exe reads some attributes through range-checked getters. A value outside
the range is clamped AND reported through the XML error logger
("| Clamping node %s value %d (maximum is %d)"). The first in-game test of the
safe set crashed on "Single player", the screen that loads the trucks of the
maps, and three mods were outside these limits:

  attribute                         exe limit          1.0.0 value
  TruckData FuelCapacity            max 64000 (int)    100000    Infinite Fuel
  TruckData/Damage Capacity         max 64000 (int)    1000000   No Damage
  TruckData/Motor Torque            max 1000000        up to 2400000 (x10) Hyper Power
  WheelFriction Substance/Body      0.1 .. 10.0        up to 4.5, fine

Found in MudRunner.exe 0.6.8: for FuelCapacity and Damage/Capacity the code
does `cmp reg, 0xFA00` and passes 0xFA00 to the "maximum is %d" message; Torque
and the wheel frictions go through one float getter (min in xmm3, max on the
stack), loaded from constants 1000000.0, 0.1 and 10.0 next to the attribute
name. read_exe_limits() finds these numbers again in the installed exe, so a
game update that changes them makes the tests fail instead of the game.

Every value a mod writes must stay inside LIMITS (tools/build_mods.py checks it).
"""

import re
import struct

# key: (element tag, attribute) -> (minimum or None, maximum or None)
LIMITS = {
    ("TruckData", "FuelCapacity"): (None, 64000),
    ("Damage", "Capacity"): (None, 64000),
    ("Motor", "Torque"): (None, 1000000.0),
    ("WheelFriction", "SubstanceFriction"): (0.1, 10.0),
    ("WheelFriction", "BodyFriction"): (0.1, 10.0),
    # gear speeds (TruckData/Motor reader 0x1408a07f5: one getter for ReverseGear, every
    # Gear and HighGear, min 0.1 in xmm12, max 32.0 loaded into xmm6 before the loop)
    ("Gear", "AngVel"): (0.1, 32.0),
    ("HighGear", "AngVel"): (0.1, 32.0),
    ("ReverseGear", "AngVel"): (0.1, 32.0),
}


def violations(tag, attrs):
    """[(attr, value, (lo, hi))] for one element's attributes outside LIMITS."""
    out = []
    for (t, a), (lo, hi) in LIMITS.items():
        if t != tag or a not in attrs:
            continue
        try:
            v = float(attrs[a])
        except ValueError:
            continue
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            out.append((a, attrs[a], (lo, hi)))
    return out


# --------------------------------------------------------------------------- reading the exe

class _Pe(object):
    def __init__(self, path):
        d = open(path, "rb").read()
        self.d = d
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        optsz = struct.unpack_from("<H", d, pe + 20)[0]
        self.base = struct.unpack_from("<Q", d, pe + 24 + 24)[0]
        self.secs = []
        o = pe + 24 + optsz
        for _ in range(nsec):
            name = d[o:o + 8].rstrip(b"\0")
            vsz, va, rsz, raw = struct.unpack_from("<IIII", d, o + 8)
            self.secs.append((name, va, vsz, raw, rsz))
            o += 40
        text = [s for s in self.secs if s[0] == b".text"][0]
        self.tva = self.base + text[1]
        self.code = d[text[3]:text[3] + text[4]]

    def off(self, va):
        for _n, sva, _vsz, raw, rsz in self.secs:
            if self.base + sva <= va < self.base + sva + rsz:
                return va - self.base - sva + raw
        return None

    def string_vas(self, s):
        out = []
        for m in re.finditer(b"\0" + re.escape(s) + b"\0", self.d):
            va = self._va(m.start() + 1)
            if va:
                out.append(va)
        return out

    def _va(self, off):
        for _n, sva, _vsz, raw, rsz in self.secs:
            if raw <= off < raw + rsz:
                return self.base + sva + off - raw
        return None

    def lea_refs(self, target_vas):
        """Code offsets of `lea reg, [rip+x]` that point at one of target_vas."""
        targets = set(target_vas)
        out = []
        for m in re.finditer(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", self.code):
            i = m.start()
            disp = struct.unpack_from("<i", self.code, i + 3)[0]
            if self.tva + i + 7 + disp in targets:
                out.append(i)
        return out

    def movss_const(self, i, xmm_prefix):
        """Float loaded by the movss at code offset i (pattern F3 [44] 0F 10 modrm disp32)."""
        n = len(xmm_prefix)
        disp = struct.unpack_from("<i", self.code, i + n)[0]
        o = self.off(self.tva + i + n + 4 + disp)
        return struct.unpack_from("<f", self.d, o)[0]


MOVSS_XMM6 = b"\xf3\x0f\x10\x35"
MOVSS_XMM7 = b"\xf3\x0f\x10\x3d"
MOV_RSP20_IMM = b"\xc7\x44\x24\x20"


def read_exe_limits(exe_path):
    """The same table as LIMITS, read from MudRunner.exe."""
    pe = _Pe(exe_path)
    out = {}

    def int_max(name):
        for i in pe.lea_refs(pe.string_vas(name)):
            seg = pe.code[i:i + 0x140]
            k = seg.find(MOV_RSP20_IMM)
            if k >= 0:
                return struct.unpack_from("<i", seg, k + 4)[0]
        return None

    out[("TruckData", "FuelCapacity")] = (None, int_max(b"FuelCapacity"))
    out[("Damage", "Capacity")] = (None, int_max(b"Damage/Capacity"))

    def last_load(i, pattern, back):
        seg = pe.code[max(0, i - back):i]
        k = seg.rfind(pattern)
        return None if k < 0 else pe.movss_const(i - len(seg) + k, pattern)

    tq = None
    for i in pe.lea_refs(pe.string_vas(b"Torque")):
        v = last_load(i, MOVSS_XMM6, 0x200)
        if v is not None and v > 1000:
            tq = v
            break
    out[("Motor", "Torque")] = (None, tq)
    for attr in ("SubstanceFriction", "BodyFriction"):
        refs = pe.lea_refs(pe.string_vas(b"WheelFriction/" + attr.encode()))
        lo = hi = None
        for i in refs:
            lo = last_load(i, MOVSS_XMM6, 0x200)
            hi = last_load(i, MOVSS_XMM7, 0x200)
            if lo is not None and hi is not None:
                break
        out[("WheelFriction", attr)] = (None if lo is None else round(lo, 4), None if hi is None else round(hi, 4))
    lo = hi = None
    for i in pe.lea_refs(pe.string_vas(b"AngVel")):
        hi = last_load(i, MOVSS_XMM6, 0xc0)
        lo = last_load(i, MOVSS_XMM12, 0x800)
        if hi is not None and lo is not None:
            break
    for tag in ("Gear", "HighGear", "ReverseGear"):
        out[(tag, "AngVel")] = (None if lo is None else round(lo, 4), hi)
    return out


MOVSS_XMM12 = b"\xf3\x44\x0f\x10\x25"


# --------------------------------------------------------------------------- the gearbox

# How the exe turns Motor Torque into wheel torque (the drivetrain update 0x140922270,
# found 16.10 for "Powerful Engines works only in 5th gear"):
#   0x1409223cf  torque of a forward Gear = Torque / powf(max(AngVel * 0.5, 1.0), 0.5),
#                so 1st gear (small AngVel) gets the most torque;
#   0x14092239e  HighGear: Torque * 1.25;
#   0x140922e9e  the torque is then multiplied by a curve of the driven wheels' angular
#                speed w: smoothstep up from AngVel*0.25-2 to AngVel (HighGear 0.35),
#                1 at w = AngVel, smoothstep DOWN to 0 at 2*AngVel+5 (HighGear AngVel+2).
# So every gear has a hard speed band: above 2*AngVel+5 the engine gives nothing,
# however big Torque is. Light trucks reach the band end of gears 1-4 with stock torque
# already, so x2.5 torque alone changed nothing there; only in 5th gear (A-469 AngVel
# 20, band end 45 rad/s) did stock torque run out first. A power mod has to raise the
# gear speeds (AngVel) too, and the sqrt above means raising AngVel by k costs sqrt(k)
# of gear torque, which the Torque factor pays back.
GEAR_HALF = 0.5          # AngVel * 0.5 ...
GEAR_FLOOR = 1.0         # ... at least 1.0 ...
GEAR_POWER = 0.5         # ... to the power 0.5 divides Torque
HIGH_GEAR_TORQUE = 1.25
BAND_SCALE, BAND_ADD = 2.0, 5.0          # band end of a Gear: 2 * AngVel + 5
HIGH_BAND_ADD = 2.0                      # band end of the HighGear: AngVel + 2


def gear_torque(torque, angvel, high=False):
    """The torque the exe gives a gear (before the speed curve)."""
    if high:
        return torque * HIGH_GEAR_TORQUE
    return torque / max(angvel * GEAR_HALF, GEAR_FLOOR) ** GEAR_POWER


def band_end(angvel, high=False):
    """Wheel angular speed (rad/s) where the gear's torque reaches 0."""
    return angvel + HIGH_BAND_ADD if high else BAND_SCALE * angvel + BAND_ADD


def read_exe_gear_rules(exe_path):
    """(half, floor, power, high torque, band scale, band add, high band add) read from the
    drivetrain update, or None. Found by its instruction pattern: `movss xmm1, [half];
    movss xmm14, [floor]; movss xmm7, [high torque]` right after the gear count, then
    `mulss xmm0, xmm1; comiss xmm0, xmm14; ...; call powf` and for the band
    `mulss xmm3, [scale]; addss xmm3, [add]`, `addss xmm0, [scale]` (high)."""
    pe = _Pe(exe_path)
    m = re.search(rb"\xf3\x0f\x10\x0d(....)\xf3\x44\x0f\x10\x35(....)\xf3\x0f\x10\x3d(....)", pe.code, re.S)
    if not m:
        return None
    i = m.start()
    half = pe.movss_const(i, b"\xf3\x0f\x10\x0d")
    floor = pe.movss_const(i + 8, b"\xf3\x44\x0f\x10\x35")
    high = pe.movss_const(i + 17, b"\xf3\x0f\x10\x3d")
    seg = pe.code[i:i + 0x100]
    # HighGear band: movaps xmm0, xmm11; addss xmm0, [c]
    k = seg.find(b"\x41\x0f\x28\xc3\xf3\x0f\x58\x05")
    # Gear band: movaps xmm3, xmm11; mulss xmm3, [c]; addss xmm3, [c]
    j = seg.find(b"\x41\x0f\x28\xdb\xf3\x0f\x59\x1d")
    if k < 0 or j < 0:
        return None
    hadd = pe.movss_const(i + k + 4, b"\xf3\x0f\x58\x05")
    scale = pe.movss_const(i + j + 4, b"\xf3\x0f\x59\x1d")
    add = pe.movss_const(i + j + 12, b"\xf3\x0f\x58\x1d")
    # the exponent of powf is xmm1 itself, the same 0.5: `mulss xmm0, xmm1`, then the
    # call with xmm1 untouched
    if seg.find(b"\xf3\x0f\x59\xc1") < 0:
        return None
    power = half
    return half, floor, power, high, scale, add, hadd


# --------------------------------------------------------------------------- archive names

# The longest package name (zip file name without ".zip") the game survives. For a
# truck (classes/trucks/<name>.xml) or a level (levels/<name>.stg) the exe asks PhysFS
# which archive the file came from (PHYSFS_getRealDir), and when that is a ".zip" it
# copies the name between the last '/' and the '.' with strncpy_s(buf, 17, ...), to
# compare it with the "%llx" ids of the loaded Workshop items. A longer name makes
# strncpy_s end the game: MSVCR110.dll+0x6d5ff, c0000409, fast fail 5 - every crash
# of the in-game tests 03.10 to 10.10 (found in the crash dumps on 11.10).
ARCHIVE_NAME_MAX = 16


def read_exe_archive_name_max(exe_path):
    """ARCHIVE_NAME_MAX read from MudRunner.exe: after `lea rdx, ".zip"` + _stricmp comes
    `lea edx, [rax+N]` (rax = 0) and `lea rcx, [rsp+x]`, the buffer size of strncpy_s."""
    pe = _Pe(exe_path)
    for i in pe.lea_refs(pe.string_vas(b".zip")):
        m = re.search(rb"\x8d\x50(.)\x48\x8d\x4c\x24", pe.code[i:i + 0x40], re.S)
        if m:
            return m.group(1)[0] - 1
    return None


# --------------------------------------------------------------------------- fuel fill thresholds

# Infinite Fuel 1.0.0 (FuelCapacity 64000) made trucks jerk and not move (11.10). The
# exe works with the FILL = fuel litres / FuelCapacity (the float at truck+0x3ec, the
# litres at +0x3e8):
#   0x1409224a5  fill < 0.06: every tick, with chance 1 - fill/0.06 (rand()/32767), the
#                engine power is cut - the "last litres" cough. At fill ~0 it is cut
#                almost every tick: the truck jerks and does not move.
#   0x1407b3e73  fill < 0.2: the red low-fuel warning.
# Fuel is set in LITRES by SetFuel (0x1408cbde0, clamps to 0..capacity) for a truck
# restored from the profile or a save (0x1408a3b2b desc.fFuel, 0x1408a3b74 start-slot
# truck) and by a fuel station (0x140791543, + litres per step). Only the parked trucks
# of a level file get a percentage (0x14070b064: clamp(fFuel/100) * capacity).
# So with 64000 l a truck brought in with its stock 80-800 l had a fill of at most
# 800/64000 = 1.25 % - deep in the cough zone, and a fuel station needs 3840 l to get out.
# The law: a truck that arrives with a full STOCK tank must stay above both thresholds,
# so the new capacity is at most stock / 0.25 (fill 25 % > 20 % > 6 %).
FUEL_COUGH_FILL = 0.06
FUEL_WARN_FILL = 0.2
FUEL_TANK_MAX_SCALE = 4


def read_exe_fuel_fills(exe_path):
    """The fill thresholds the exe compares fuel/FuelCapacity with: sorted constants of
    `divss xmmA, [rax+CAP]` + `movss xmmB, [rip+const]`, CAP read from the FuelCapacity
    reader (`movss [rax+CAP], xmm0` after the clamp)."""
    pe = _Pe(exe_path)
    cap = None
    for i in pe.lea_refs(pe.string_vas(b"FuelCapacity")):
        k = pe.code.find(b"\xf3\x0f\x11\x80", i, i + 0x100)
        if k >= 0:
            cap = struct.unpack_from("<I", pe.code, k + 4)[0]
    if cap is None:
        return None
    out = set()
    pat = rb"\xf3[\x44]?\x0f\x5e[\x80\x88\x90\x98\xa0\xa8\xb0\xb8]" + re.escape(struct.pack("<I", cap))
    for m in re.finditer(pat, pe.code):
        j = m.end()
        n = re.search(rb"\xf3[\x44]?\x0f\x10[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", pe.code[j:j + 0x10])
        if n:
            p = j + n.start()
            prefix = pe.code[p:p + n.end() - n.start()]
            out.add(round(pe.movss_const(p, prefix), 4))
    return sorted(out)


# --------------------------------------------------------------------------- garages

# The garage lock (found 11.10 for the "Plains" map, MudRunner.exe):
#   A garage is a level locator with eType 1 (levels/*.stg, see build_mods.read_stg_locators).
#   The .stg has NO lock flag for it. The lock is game state: garage points per garage
#   (the save stores numGarages x {xzOrg, numGaragePoints}, GameSTSLoad.cpp,473-478).
#   0x1406dc4d0  points a garage needs: 4, or 8 (multiplayer "hardcore" garages).
#   0x1406ccb00  AddGaragePoints(garage, n): adds up to the need; at the need the garage opens.
#   0x14070bbff  new game: every garage within GARAGE_START_RADIUS of the drive truck
#                (nDriveTruck of the .stg) gets the full need - the start garage.
#   0x1401270b3  the rest: unload cargo that carries garage points ("GaragePoints" in the
#                truck/addon XML, "Carries %d garage points") at the garage.
# So a file mod cannot open the other garages: the exe gives free points only by
# distance to the one drive truck, and the need is code, not data.
GARAGE_NEED = (4, 8)
GARAGE_START_RADIUS = 64.0


def read_exe_garage_rules(exe_path):
    """(need points, start radius) read from MudRunner.exe, or None.

    need: the function `cmp byte [rcx+0xf0], 0; mov eax, A; jne +5; mov eax, B;
    add rsp, 0x28; ret` gives (B, A). radius: the float of `movss xmm1, [rip+x];
    comiss xmm1, xmm0; jbe; call <that function>` (the new-game garage loop)."""
    pe = _Pe(exe_path)
    m = re.search(rb"\x80\xb9\xf0\x00\x00\x00\x00\xb8(.)\x00\x00\x00\x75\x05\xb8(.)\x00\x00\x00"
                  rb"\x48\x83\xc4\x28\xc3", pe.code, re.S)
    if not m:
        return None
    need = (m.group(2)[0], m.group(1)[0])
    fn = pe.code.rfind(b"\x48\x83\xec\x28", 0, m.start())     # sub rsp, 0x28: its start
    if fn < 0 or m.start() - fn > 0x40:
        return None
    radius = None
    for k in re.finditer(rb"\xf3\x0f\x10\x0d....\x0f\x2f\xc8\x76.\xe8", pe.code, re.S):
        call = k.end() - 1
        target = call + 5 + struct.unpack_from("<i", pe.code, call + 1)[0]
        if target == fn:
            radius = pe.movss_const(k.start(), b"\xf3\x0f\x10\x0d")
    if radius is None:
        return None
    return need, radius


# --------------------------------------------------------------------------- map locks

# Map locks (found 16.10, MudRunner.exe): 0x14076fdf0 fills a map's lock info from a table in
# the CODE - `lea rdx, "level_x"; call strcmp; jne next; mov dword [rdi], index;
# mov dword [rdi+0xc], need` (no `mov [rdi+0xc], imm` = need 0, the shared tail writes ebx=0).
# The lock (0x14009b139, 0x14076d42e): need > profile.numLogPoints and the map's
# status.nMinCompleteBalance == 0. profile.numLogPoints is read only by the STU loader
# (0x1407e3efa) - so it is the profile field the unlock tool sets.
MAP_LOG_POINTS = {"level_plains": 0, "level_volcano": 0, "level_coast": 1, "level_river": 2,
                  "level_hill": 2, "level_flood": 3, "level_valley": 0, "level_ridge": 0,
                  "level_dlc3_01": 0, "level_dlc3_02": 1, "level_dlc4_01": 0}


def read_exe_map_requirements(exe_path):
    """{level name: log points it needs} read from MudRunner.exe, or None."""
    pe = _Pe(exe_path)
    anchor = None
    # the string may be the tail of a longer one (pooled), so resolve every candidate lea
    for m in re.finditer(rb"\x48\x8d\x15.{4}.{0,40}?\xc7\x47\x0c\x01\x00\x00\x00", pe.code, re.S):
        i = m.start()
        o = pe.off(pe.tva + i + 7 + struct.unpack_from("<i", pe.code, i + 3)[0])
        if o is not None and pe.d[o:o + 12] == b"level_coast\0":
            anchor = i
    if anchor is None:
        return None
    leas = []
    for m in re.finditer(rb"\x48\x8d\x15", pe.code[anchor - 0x80:anchor + 0x180]):
        i = anchor - 0x80 + m.start()
        va = pe.tva + i + 7 + struct.unpack_from("<i", pe.code, i + 3)[0]
        o = pe.off(va)
        if o is None:
            continue
        name = pe.d[o:o + 40].split(b"\0")[0]
        if name.startswith(b"level_"):
            leas.append((i, name.decode("ascii")))
    out = {}
    for k, (i, name) in enumerate(leas):
        end = leas[k + 1][0] if k + 1 < len(leas) else i + 0x40
        block = pe.code[i:end]
        j = block.find(b"\xc7\x47\x0c")
        out[name] = struct.unpack_from("<I", block, j + 3)[0] if j >= 0 else 0
    return out or None
