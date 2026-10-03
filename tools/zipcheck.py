"""Can MudRunner's file system read this zip? Checks the rules of PhysFS 2.0.

MudRunner mounts archives with PhysFS 2.0 (the exe carries its messages
"ZIP bigger than 2 gigs?!", "Corrupted archive", "buffer must fit in
32-bits"). That reader has no Zip64 support, and before it reads a file it
compares the file's local header with the central directory: "version needed",
compression method, and CRC / compressed / uncompressed size (a zero there is
allowed). Any difference -> ERR_CORRUPTED, the file cannot be opened, and the
game does not fall back to the copy in Media.zip: the first archive that lists
a path owns it.

The 1.0.0 build of Unlocked Trucks broke exactly this: Python's streaming
writer (ZipFile.open(..., force_zip64=True)) wrote local headers with version
45 and sizes 0xFFFFFFFF plus a Zip64 extra field, while the central directory
held the real sizes. In game the six level files became unreadable.

  python tools/zipcheck.py some.zip [more.zip ...]
"""

import os
import struct
import sys
import zipfile

LOCAL_SIG = 0x04034B50
MAX_ARCHIVE = 2 ** 31 - 1


def problems(path):
    """List of reasons why PhysFS 2.0 would fail on this archive (empty = fine)."""
    out = []
    size = os.path.getsize(path)
    if size > MAX_ARCHIVE:
        out.append("archive is %d bytes, PhysFS 2.0 stops at 2 GB" % size)
    with open(path, "rb") as fh:
        fh.seek(max(0, size - 66000))
        tail = fh.read()
    if b"PK\x06\x06" in tail or b"PK\x06\x07" in tail:
        out.append("Zip64 end of central directory record")
    with zipfile.ZipFile(path) as z, open(path, "rb") as fh:
        for info in z.infolist():
            name = info.filename
            if info.extract_version > 20:
                out.append("%s: central 'version needed' %d (> 2.0)" % (name, info.extract_version))
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                out.append("%s: compression method %d" % (name, info.compress_type))
            if info.file_size >= 0xFFFFFFFF or info.compress_size >= 0xFFFFFFFF:
                out.append("%s: size needs Zip64" % name)
            if _has_zip64_extra(info.extra):
                out.append("%s: Zip64 extra field in the central directory" % name)
            fh.seek(info.header_offset)
            head = fh.read(30)
            if len(head) < 30:
                out.append("%s: truncated local header" % name)
                continue
            sig, ver, _flags, meth, _t, _d, crc, csz, usz, nlen, elen = struct.unpack("<IHHHHHIIIHH", head)
            if sig != LOCAL_SIG:
                out.append("%s: no local header signature" % name)
                continue
            extra = fh.read(nlen + elen)[nlen:]
            if ver != info.extract_version:
                out.append("%s: local 'version needed' %d != central %d" % (name, ver, info.extract_version))
            if meth != info.compress_type:
                out.append("%s: local method %d != central %d" % (name, meth, info.compress_type))
            if crc and crc != info.CRC:
                out.append("%s: local CRC differs from central" % name)
            if csz and csz != info.compress_size:
                out.append("%s: local compressed size 0x%x != central %d" % (name, csz, info.compress_size))
            if usz and usz != info.file_size:
                out.append("%s: local size 0x%x != central %d" % (name, usz, info.file_size))
            if _has_zip64_extra(extra):
                out.append("%s: Zip64 extra field in the local header" % name)
    return out


def _has_zip64_extra(extra):
    i = 0
    while i + 4 <= len(extra):
        tag, ln = struct.unpack_from("<HH", extra, i)
        if tag == 0x0001:
            return True
        i += 4 + ln
    return False


def main(paths):
    bad = 0
    for p in paths:
        pr = problems(p)
        print("%s: %s" % (p, "ok" if not pr else "%d problems" % len(pr)))
        for x in pr[:20]:
            print("   ", x)
        bad += bool(pr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
