"""Mutation check: break the product on purpose, the named test must fail.

  .venv\\Scripts\\python tools\\mutation_check.py            # all mutations
  .venv\\Scripts\\python tools\\mutation_check.py 3 7        # only these numbers

Each mutation runs in a fresh temp copy of the repository (tracked and new,
not ignored files), so the working tree is never touched. A mutation is
"caught" when the listed test fails on the mutated copy. A green suite that
does not catch these means nothing.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (file, old text, new text, test module pattern, test name filter)
MUTATIONS = [
    ("mods/no_damage/mod.json", '"set": "64000"', '"set": "1000"', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("mods/infinite_fuel/mod.json", '"set": "64000"', '"set": "0"', "test_mods.py", "test_no_zero_divisors"),
    ("mods/powerful_engines/mod.json", '"scale": 2.5', '"scale": 2.0', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("mods/order.json", '"hyper_power": [\n      "powerful_engines"\n    ]', '"hyper_power": []', "test_mods.py",
     "test_hyper_power_is_not_stacked"),
    ("mods/awd_difflock/mod.json", '"none": "full",\n        "": "full"', '"none": "full"', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("mods/awd_difflock/mod.json", '"None": "Default"', '"Always": "Always"', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("mods/grippy_wheels/mod.json", '"scale": 2.5,\n      "min": 2.5', '"scale": 2.5', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("mods/deep_fording/mod.json", '"lift": 1.0', '"lift": 0.5', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("mods/strong_winch/mod.json", '"stump_b"', '"stump_a"', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("tools/build_mods.py", "if n not in replaces.get(name, [])]", "if False]",
     "test_mods.py", "test_chain_upper_carries_lower"),
    ("tools/build_mods.py", 'buf[r["locked_at"]] = 0', 'buf[r["locked_at"] + 1] = 0', "test_mods.py",
     "test_unlock_changes_only_lock_bytes"),
    ("tools/build_mods.py", "        if n:                      # levels without", "        if True:  # levels without",
     "test_mods.py", "test_unlock_changes_only_lock_bytes"),
    ("tools/mrxml.py", 'if c.attrs.get("_inheritRemove") == "true":\n                    removed.add',
     'if False:\n                    removed.add', "test_xml.py", "test_positional_merge_and_remove"),
    ("tools/mrxml.py", "            merged.attrs.update(own_attrs)", "            pass", "test_xml.py",
     "test_templates_local_chain_and_include"),
    ("tools/mrxml.py", '        c.raw_index = counts.get(c.tag, 0)', '        c.raw_index = 0',
     "test_workshop.py", "test_variants_resolve_to_the_mod_values"),
    ("tools/build_workshop.py", 'encoding="utf-8", newline="\\r\\n") as fh:\n            fh.write(desc)',
     'encoding="utf-8", newline="\\n") as fh:\n            fh.write(desc)', "test_workshop.py",
     "test_copy_paste_files_use_crlf"),
    ("tools/build_workshop.py", 'return fs.source(mrxml.KIND_DIRS[kind] + name + ".xml") == "Media.zip"',
     "return True", "test_workshop.py", "test_base_game_trucks_only"),
    ("tools/build_workshop.py", '                    lines.append("%s<%s />" % (ind, tag))\n',
     "", "test_workshop.py", "test_child_xml_placeholders"),
    ("tools/install_local.py", "return text[:m.start()] + block + text[m.start():]",
     "return text[:m.end()] + block + text[m.end():]", "test_install.py", "test_lines_go_above_media_zip_in_order"),
    ("README.md", "# MudRunnerMods", "# MudRunnerMods\nmail: someone@gm" + "ail.com", "test_privacy.py",
     "test_repository_files"),
    ("tools/mrxml.py", '        s += ".0"', "        pass", "test_xml.py", "test_fmt_num"),
    ("tools/build_mods.py", 'z.open(zi, "w") as dst', 'z.open(zi, "w", force_zip64=True) as dst', "test_mods.py",
     "test_stream_copy"),
    ("tools/install_local.py", "skip = [] if include_opt_in else opt_in()", "skip = []", "test_install.py",
     "test_default_is_the_safe_set_and_says_so"),
    ("mods/infinite_fuel/mod.json", '"set": "64000"', '"set": "100000"', "test_limits.py",
     "test_every_mod_value_within_limits"),
    ("mods/hyper_power/mod.json", ',\n      "max": 1000000', "", "test_limits.py", "test_every_mod_value_within_limits"),
    ("tools/engine_limits.py", '("Damage", "Capacity"): (None, 64000),', '("Damage", "Capacity"): (None, 6400000),',
     "test_limits.py", "test_limits_match_the_exe"),
]


def copy_repo(dst):
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         capture_output=True, timeout=60, check=True).stdout.decode("utf-8")
    for rel in out.split("\0"):
        if not rel or not os.path.isfile(os.path.join(ROOT, rel)):
            continue
        target = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), target)


def run_one(i, m, python):
    path, old, new, pattern, name = m
    tmp = tempfile.mkdtemp(prefix="mrmut_")
    try:
        copy_repo(tmp)
        full = os.path.join(tmp, path)
        with open(full, encoding="utf-8", newline="") as fh:
            text = fh.read()
        if text.count(old) != 1:
            return "BROKEN", "mutation text found %d times in %s" % (text.count(old), path)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text.replace(old, new))
        t0 = time.time()
        r = subprocess.run([python, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-k", name],
                           cwd=tmp, capture_output=True, text=True, timeout=1800)
        ran = "Ran 0 tests" not in r.stderr
        if not ran:
            return "BROKEN", "no test matched " + name
        return ("CAUGHT" if r.returncode != 0 else "MISSED"), "%.0f s" % (time.time() - t0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)        # the temp copy made above


def main():
    pick = [int(x) for x in sys.argv[1:]]
    python = sys.executable
    results = []
    for i, m in enumerate(MUTATIONS, 1):
        if pick and i not in pick:
            continue
        status, info = run_one(i, m, python)
        results.append(status)
        print("%2d %-7s %-28s -> %-44s %s" % (i, status, m[0], m[4], info), flush=True)
    caught = results.count("CAUGHT")
    print("caught %d of %d" % (caught, len(results)))
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
