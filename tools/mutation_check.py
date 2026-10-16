"""Mutation check: break the product on purpose, the named test must fail.

  .venv\\Scripts\\python tools\\mutation_check.py            # all mutations
  .venv\\Scripts\\python tools\\mutation_check.py 3 7        # only these numbers

Each mutation runs in a fresh temp copy of the repository (tracked and new,
not ignored files), so the working tree is never touched. A mutation is
"caught" when the listed test fails on the mutated copy. A green suite that
does not catch these means nothing.

(The old chain mutation is gone: since the truck mods ship heir classes, no two
packages share a path, so breaking the chain changes no output.)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (file, old text, new text, test module pattern, test name filter), or for a mutation
# that needs several edits at once: ([(file, old, new), ...], pattern, name)
NO_GUARD = ("tools/build_mods.py",
            '    return sorted(p for p in files if fs.exists(p) and (heir or p.startswith(mrxml.KIND_DIRS["trucks"])))',
            "    return []")       # the build's own guard off: the law test must catch it alone
MUTATIONS = [
    ("mods/no_damage/mod.json", '"set": "64000"', '"set": "1000"', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("mods/infinite_fuel/mod.json", '"scale": 4', '"scale": 0', "test_mods.py", "test_no_zero_divisors"),
    ("mods/powerful_engines/mod.json", '"scale": 3\n', '"scale": 2.5\n', "test_mods.py",
     "test_each_mod_alone_patches_every_target"),
    ("tools/build_mods.py", "        clash = conflicts(names)\n", "        clash = []\n",
     "test_mods.py", "test_custom_package_has_exactly_the_chosen_mods"),
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
    ("tools/build_mods.py", 'buf[r["locked_at"]] = 0', 'buf[r["locked_at"] + 1] = 0', "test_mods.py",
     "test_unlock_changes_only_lock_bytes"),
    ("tools/build_mods.py", "        if n:                      # levels without", "        if True:  # levels without",
     "test_mods.py", "test_unlock_changes_only_lock_bytes"),
    ("tools/mrxml.py", 'if c.attrs.get("_inheritRemove") == "true":\n                    removed.add',
     'if False:\n                    removed.add', "test_xml.py", "test_positional_merge_and_remove"),
    ("tools/mrxml.py", "            merged.attrs.update(own_attrs)", "            pass", "test_xml.py",
     "test_templates_local_chain_and_include"),
    # full copies (10.10; raw_index only served the old thin heirs): a copy that loses an element
    ("tools/mrxml.py", "    for c in node.children:\n        out.append(serialize(c, depth + 1))",
     "    for c in node.children[:-1]:\n        out.append(serialize(c, depth + 1))",
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
    ([("mods/infinite_fuel/mod.json", '"scale": 4,', '"scale": 200,'),
      ("mods/infinite_fuel/mod.json", '"max": 64000', '"max": 100000')], "test_limits.py",
     "test_every_mod_value_within_limits"),
    # Infinite Fuel 1.0.0 (11.10): a 64000 l tank made trucks from the profile/save cough and not move
    ("mods/infinite_fuel/mod.json", '"scale": 4,', '"scale": 80,', "test_limits.py",
     "test_full_stock_tank_is_not_near_empty"),
    ("tools/engine_limits.py", "FUEL_TANK_MAX_SCALE = 4", "FUEL_TANK_MAX_SCALE = 6", "test_limits.py",
     "test_thresholds_order"),
    ("mods/hyper_power/mod.json", ',\n      "max": 1000000', "", "test_limits.py", "test_every_mod_value_within_limits"),
    ("tools/engine_limits.py", '("Damage", "Capacity"): (None, 64000),', '("Damage", "Capacity"): (None, 6400000),',
     "test_limits.py", "test_limits_match_the_exe"),
    # third in-game test: replacing a stock truck file crashed "Single player"
    ("mods/infinite_fuel/mod.json", '"as_heirs": true', '"as_heirs": false', "test_mods.py",
     "test_no_package_replaces_a_stock_truck_file"),
    # (updated 10.10: the copies are picked in plan_variants since the full-copy change)
    ("tools/build_workshop.py", "if include_dlc or base_game(fs, k[0], k[1])}", "if base_game(fs, k[0], k[1])}",
     "test_mods.py", "test_dlc_trucks_have_heirs"),
    # fifth in-game test (10.10): the law "no mod writes to classes/trucks/<stock name>.xml"
    ([("mods/infinite_fuel/mod.json", '"as_heirs": true', '"as_heirs": false'), NO_GUARD],
     "test_truck_law.py", "test_no_mod_writes_a_stock_truck_file"),
    ([("tools/build_workshop.py", '        new = "%s_%s" % (prefix, cls)', "        new = cls"), NO_GUARD],
     "test_truck_law.py", "test_no_mod_writes_a_stock_truck_file"),
    ([("tools/build_mods.py", """            if n in heirs:
                touched[n] = set()
                continue""", """            if False:
                touched[n] = set()
                continue"""), NO_GUARD],
     "test_truck_law.py", "test_no_mod_writes_a_stock_truck_file"),
    ("tools/build_workshop.py", '        new = "%s_%s" % (prefix, cls)', "        new = cls",
     "test_truck_law.py", "test_workshop_folders"),
    ("tools/build_workshop.py", "    for lang in languages(fs):\n        names = stock_names(fs, lang)",
     "    for lang in languages(fs)[:1]:\n        names = stock_names(fs, lang)",
     "test_truck_law.py", "test_new_trucks_have_names_in_every_language"),
    ("tools/build_workshop.py", '        suffix = suffix_ru if lang == "ru" and suffix_ru else suffix_en',
     "        suffix = suffix_en", "test_truck_law.py", "test_new_trucks_have_names_in_every_language"),
    ("tools/install_local.py", '"file: diagnosis only, the game may crash (with the old long names they always did)")',
     '"file")', "test_install.py", "test_help_marks_the_crashing_probes"),
    # the real crash cause (dumps, 11.10): package name > 16 characters before .zip
    ("mods/infinite_fuel/mod.json", '"package": "opentrail_fuel"', '"package": "opentrail_infinite_fuel"',
     "test_archive_names.py", "test_every_package_name_fits"),
    ("tools/engine_limits.py", "ARCHIVE_NAME_MAX = 16", "ARCHIVE_NAME_MAX = 32",
     "test_archive_names.py", "test_limit_matches_the_exe"),
    ([("tools/build_mods.py", "    bad_name = archive_name_problem(out_path)", "    bad_name = None"),
      ("mods/no_damage/mod.json", '"package": "opentrail_damage"', '"package": "OpenTrail_No_Damage"')],
     "test_archive_names.py", "test_written_class_packages"),
    ("tools/install_local.py", ".lower().startswith(MARKS)", ".startswith(MARKS)",
     "test_archive_names.py", "test_old_long_names_are_still_removed"),
    # level locators and garages (11.10): the format after the trucks, the per-map law, the exe rules
    ("tools/build_mods.py", "        if typ in ATTACHED_LOCATORS:", "        if typ == 7:",
     "test_mods.py", "test_locators_of_every_level_parse"),
    ("tools/build_mods.py", '        if r["locked"]:', '        if r["locked"] and r["type"]:',
     "test_mods.py", "test_no_locked_truck_on_any_map_after_the_mod"),
    ("tools/engine_limits.py", "GARAGE_START_RADIUS = 64.0", "GARAGE_START_RADIUS = 100.0",
     "test_limits.py", "test_garage_rules_match_the_exe"),
    ("tools/build_mods.py", "            < engine_limits.GARAGE_START_RADIUS",
     "            < 1000.0", "test_mods.py", "test_plains_lock_is_a_garage_not_a_truck"),
    # 16.10: power felt only in 5th gear - the gears' speed band (engine_limits.gear_torque/band_end)
    ("mods/powerful_engines/mod.json", '"path": "TruckData/Motor/Gear",\n      "attr": "AngVel",\n      "scale": 1.5',
     '"path": "TruckData/Motor/Gear",\n      "attr": "AngVel",\n      "scale": 1.0', "test_mods.py",
     "test_power_mods_are_felt_in_every_gear"),
    ("mods/hyper_power/mod.json", '"path": "TruckData/Motor/HighGear",\n      "attr": "AngVel",\n      "scale": 2,',
     '"path": "TruckData/Motor/HighGear",\n      "attr": "AngVel",\n      "scale": 1,', "test_mods.py",
     "test_power_mods_are_felt_in_every_gear"),
    ("tools/engine_limits.py", "GEAR_POWER = 0.5 ", "GEAR_POWER = 0.0 ", "test_limits.py",
     "test_gear_rules_match_the_exe"),
    ("tools/engine_limits.py", '("Gear", "AngVel"): (0.1, 32.0),', '("Gear", "AngVel"): (0.1, 64.0),',
     "test_limits.py", "test_limits_match_the_exe"),
    # 16.10: your own set (tools/combine.py) - sum of the parts, conflicts are a choice
    ("tools/build_mods.py", "            if common:\n", "            if False:\n", "test_combine.py",
     "test_power_mods_conflict_and_nothing_else_does"),
    ("tools/build_mods.py", '            for x in specs:\n                combo["ops"].extend(x["ops"])',
     '            for x in specs[:1]:\n                combo["ops"].extend(x["ops"])', "test_combine.py",
     "test_everything_compatible_in_one_truck"),
    ("tools/build_mods.py", 'CUSTOM_SUFFIX_RU = "Свой набор"', 'CUSTOM_SUFFIX_RU = "Custom"', "test_combine.py",
     "test_names_and_package"),
    ("tools/combine.py", "        names.remove(b if keep == a else a)", "        names.remove(keep)", "test_combine.py",
     "test_conflict_is_a_choice_not_an_overwrite"),
    ("tools/install_local.py", "        packages = [custom]\n", "        packages = []\n", "test_install.py",
     "test_custom_set_alone_and_removable"),
    # 16.10: the big tank adds no mass (only a FuelMass block does)
    ("tools/build_workshop.py", "            node.attrs[attr] = value\n        out[(kind, new)]",
     "            node.attrs[attr] = value\n        if prefix == \"otf\":\n"
     "            root.find(\"PhysicsModel/Body\")[0].attrs[\"Mass\"] = \"9999\"\n        out[(kind, new)]",
     "test_limits.py", "test_big_tank_copies_have_no_fuel_mass_and_stock_mass"),
    # 16.10: profile unlock tool (UserProfile.stu)
    ("tools/profile_stu.py", "    out[\"numLogPoints_at\"] = r.p\n", "    out[\"numLogPoints_at\"] = r.p + 1\n",
     "test_profile.py", "test_edit_law_synthetic"),
    ("tools/profile_stu.py", "            m[\"isAllGaragesUnlocked\"] = r.u8(\"isAllGaragesUnlocked\")\n", "",
     "test_profile.py", "test_synthetic_profile_parses_to_the_end"),
    ("tools/unlock_profile.py", "    bk = make_backup(profile)\n    write_atomic(profile, new)",
     "    bk = profile\n    write_atomic(profile, new)", "test_profile.py",
     "test_write_makes_backup_and_restore_brings_it_back"),
    ("tools/unlock_profile.py", "    if not ask_yes(\"Записать изменения в профиль?\", assume_yes):",
     "    if False:", "test_profile.py", "test_no_without_confirmation"),
    ("tools/unlock_profile.py", "    if install_local.game_running():", "    if False:", "test_profile.py",
     "test_refuses_while_game_runs"),
    ("tools/engine_limits.py", "\"level_flood\": 3,", "\"level_flood\": 2,", "test_profile.py",
     "test_table_matches_the_exe"),
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


def edits_of(m):
    """[(file, old, new)], test pattern, test name of a mutation entry."""
    if isinstance(m[0], list):
        return m[0], m[1], m[2]
    return [m[:3]], m[3], m[4]


def run_one(i, m, python):
    edits, pattern, name = edits_of(m)
    tmp = tempfile.mkdtemp(prefix="mrmut_")
    try:
        copy_repo(tmp)
        for path, old, new in edits:
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
        edits, _pattern, name = edits_of(m)
        print("%2d %-7s %-28s -> %-44s %s" % (i, status, "+".join(e[0] for e in edits)[:28], name, info),
              flush=True)
    caught = results.count("CAUGHT")
    print("caught %d of %d" % (caught, len(results)))
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
