"""MudRunner profile UserProfile.stu: reader and the few edits the unlock tool makes.

The layout is the one MudRunner.exe 0.6.8 reads in its STU loader (0x1407e3a00..0x1407e5050,
SpinTiresCommon.cpp lines 2212-2323, field names from the "Cant read ..." strings). No checksum,
no compression of the whole file, no encryption: the loader reads the file into a buffer and
takes fields one after another.

  u32 nFileVersion        accepted: 0x133c7e2 0x133c904 0x133c90c 0x133c962 0x133c96b 0x133c9dd 0x133ee19
  str profile.strLevelContinue, str profile.strLevelLast
  str profile.strAutoDevTruck                      (version >= 0x133c90c)
  u8  isFirstLaunch, isProposeChallenges, isNavigationHints, isDefaultHardcore, isCertifiedModsOnly
  u32 profile.numLogPoints                         <- map locks compare with this (0x14009b139)
  u32 numChallenges x { str id, 8 bytes }
  u32 numMaps x {
      str strId, str status.strLastPlayed, f32 status.fSavePlayTime, u8 status.isSaveHardcore,
      u32 numActiveTrucks, numActiveTrucks x 12 bytes status.unlockedTrucks,
      u32 numStartupTrucks x { u16 first, str second },
      str status.strContinueTrucks                 (version >= 0x133c962)
      u32 nMiniCloakingWidth, u32 nMiniCloakingHeight,
      if w*h: u32 nCompressSize, nCompressSize bytes (zlib, the fog of war)
      u32 status.nMinCompleteBalance, u8 status.isCompleteHardcore,
      u8 status.isAllGaragesUnlocked, u8 status.isAllWatchpointsReached   (version >= 0x133c9dd)
  }
  str profile.strMultiSaveGUID, str profile.strMultiSaveLevel,
  u8 isMultiSaveFriendsOnly, u8 isMultiSaveHardcore,
  u32 n (<= 0x400) x { u16, str }                  multiSaveStartupTrucks
  u32 n (<= 0x400) x { u64, str }                  multiSaveServerMods (version >= 0x133c9dd)
  u32 nBufferSettingsSize + bytes, u32 nBufferControlsSize + bytes

str = u16 length (with the closing zero byte, never 0) + that many bytes.

Map locks (0x14076fdf0, table in the exe code, not in game files): a map is locked when its
required log points > profile.numLogPoints and its status.nMinCompleteBalance == 0.
Required points: level_coast 1, level_river 2, level_hill 2, level_flood 3, level_dlc3_02 1,
all others 0 (read from the exe by engine_limits.read_exe_map_requirements).
"""
import struct

VERSIONS = (0x133c7e2, 0x133c904, 0x133c90c, 0x133c962, 0x133c96b, 0x133c9dd, 0x133ee19)
LIST_MAX = 0x400
BUFFER_MAX = 0x40000000


class StuError(ValueError):
    pass


class _R(object):
    def __init__(self, data):
        self.d = data
        self.p = 0

    def take(self, n, what):
        if n < 0 or self.p + n > len(self.d):
            raise StuError("%s: file ends at %d (need %d bytes)" % (what, self.p, n))
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def u8(self, what):
        return self.take(1, what)[0]

    def u16(self, what):
        return struct.unpack("<H", self.take(2, what))[0]

    def u32(self, what):
        return struct.unpack("<I", self.take(4, what))[0]

    def f32(self, what):
        return struct.unpack("<f", self.take(4, what))[0]

    def s(self, what):
        n = self.u16(what)
        if n == 0:
            raise StuError("%s: string length 0" % what)
        return self.take(n, what)[:n - 1].decode("latin-1")


def parse(data):
    """Return a dict with the fields and byte offsets the edits need. Raises StuError."""
    r = _R(bytes(data))
    out = {"maps": [], "challenges": []}
    ver = r.u32("nFileVersion")
    if ver not in VERSIONS:
        raise StuError("unknown profile version 0x%x" % ver)
    out["version"] = ver
    out["strLevelContinue"] = r.s("strLevelContinue")
    out["strLevelLast"] = r.s("strLevelLast")
    out["strAutoDevTruck"] = r.s("strAutoDevTruck") if ver >= 0x133c90c else None
    for k in ("isFirstLaunch", "isProposeChallenges", "isNavigationHints", "isDefaultHardcore",
              "isCertifiedModsOnly"):
        out[k] = r.u8(k)
    out["numLogPoints_at"] = r.p
    out["numLogPoints"] = r.u32("numLogPoints")
    for _ in range(r.u32("numChallenges")):
        cid = r.s("challenge id")
        out["challenges"].append((cid, r.take(8, "challenge data")))
    for _ in range(r.u32("numMaps")):
        m = {"start": r.p}
        m["strId"] = r.s("strId")
        m["strLastPlayed"] = r.s("strLastPlayed")
        m["fSavePlayTime"] = r.f32("fSavePlayTime")
        m["isSaveHardcore"] = r.u8("isSaveHardcore")
        m["numActiveTrucks_at"] = r.p
        n = r.u32("numActiveTrucks")
        m["unlockedTrucks_at"] = r.p
        m["unlockedTrucks"] = [r.take(12, "unlockedTrucks") for _ in range(n)]
        m["startupTrucks"] = []
        for _ in range(r.u32("numStartupTrucks")):
            first = r.u16("startupTrucks first")
            m["startupTrucks"].append((first, r.s("startupTrucks second")))
        m["strContinueTrucks"] = r.s("strContinueTrucks") if ver >= 0x133c962 else None
        w = r.u32("nMiniCloakingWidth")
        h = r.u32("nMiniCloakingHeight")
        m["cloaking"] = (w, h)
        m["cloak"] = b""
        if w * h:
            size = r.u32("nCompressSize")
            if size > BUFFER_MAX:
                raise StuError("nCompressSize too big")
            m["cloak"] = r.take(size, "compressedBuffer")
        m["nMinCompleteBalance"] = r.u32("nMinCompleteBalance")
        m["isCompleteHardcore"] = r.u8("isCompleteHardcore")
        m["isAllGaragesUnlocked_at"] = None
        if ver >= 0x133c9dd:
            m["isAllGaragesUnlocked_at"] = r.p
            m["isAllGaragesUnlocked"] = r.u8("isAllGaragesUnlocked")
            m["isAllWatchpointsReached"] = r.u8("isAllWatchpointsReached")
        m["end"] = r.p
        out["maps"].append(m)
    out["strMultiSaveGUID"] = r.s("strMultiSaveGUID")
    out["strMultiSaveLevel"] = r.s("strMultiSaveLevel")
    out["isMultiSaveFriendsOnly"] = r.u8("isMultiSaveFriendsOnly")
    out["isMultiSaveHardcore"] = r.u8("isMultiSaveHardcore")
    n = r.u32("numStartupTrucks")
    if n > LIST_MAX:
        raise StuError("numStartupTrucks too big")
    out["multiSaveStartupTrucks"] = [(r.u16("first"), r.s("second")) for _ in range(n)]
    out["multiSaveServerMods"] = []
    if ver >= 0x133c9dd:
        n = r.u32("numServerMods")
        if n > LIST_MAX:
            raise StuError("numServerMods too big")
        for _ in range(n):
            mid = struct.unpack("<Q", r.take(8, "server mod id"))[0]
            out["multiSaveServerMods"].append((mid, r.s("server mod name")))
    for k in ("settings", "controls"):
        size = r.u32("nBuffer size")
        if size > BUFFER_MAX:
            raise StuError("buffer too big")
        out[k] = r.take(size, k)
    if r.p != len(r.d):
        raise StuError("%d extra bytes after the last field" % (len(r.d) - r.p))
    return out


def set_log_points(data, points):
    """Copy of data with profile.numLogPoints = points (4 bytes in place)."""
    p = parse(data)
    o = p["numLogPoints_at"]
    return bytes(data[:o]) + struct.pack("<I", points) + bytes(data[o + 4:])


def set_all_garages_flag(data, value=1):
    """Copy of data with status.isAllGaragesUnlocked = value on every map (1 byte each, in place)."""
    p = parse(data)
    b = bytearray(data)
    for m in p["maps"]:
        if m["isAllGaragesUnlocked_at"] is not None:
            b[m["isAllGaragesUnlocked_at"]] = value
    return bytes(b)


def locked_maps(profile, requirements):
    """Names of maps the game shows locked: required > numLogPoints and nMinCompleteBalance == 0.
    requirements: {map name: points}. Maps without a profile entry have balance 0."""
    balance = {m["strId"]: m["nMinCompleteBalance"] for m in profile["maps"]}
    return sorted(n for n, need in requirements.items()
                  if need > profile["numLogPoints"] and balance.get(n, 0) == 0)
