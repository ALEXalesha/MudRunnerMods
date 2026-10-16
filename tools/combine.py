"""Your own set: several OpenTrail mods in ONE copy of every truck.

  python tools/combine.py                                   # asks in Russian: numbers, conflicts, install
  python tools/combine.py --mods infinite_fuel,powerful_engines,no_damage --install
  python tools/combine.py --remove                          # take every OpenTrail line out of the game
  python tools/combine.py --list

"Собрать свой мод.bat" in the repository root starts the first form.

What it builds: build/custom/opentrail_custom.zip (16 characters, the most the game
takes, see engine_limits.ARCHIVE_NAME_MAX). Every truck mod you pick goes into one
new copy of each truck, otc_<truck>, named "<truck> (Свой набор)" ("(Custom)" in the
other languages); wheel, winch and map mods go in as in their own packages. The law
(tests/test_combine.py): the combined copy has exactly the values each chosen mod
gives on its own, and everything else stays stock.

Mods that change the same value cannot both win: Powerful Engines and Hyper Power
both set the engine torque and the gear speeds. Then the script asks which one to
keep (with --mods it stops and names both) instead of quietly letting one overwrite
the other (build_mods.conflicts).

Install = tools/install_local.py --custom --apply (the game must be closed; a backup
of Config.xml is written first). Undo = --remove (or install_local.py --remove --apply).
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_mods  # noqa: E402

OUT = os.path.join(build_mods.ROOT, "build", "custom")
INSTALL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "install_local.py")


class CombineError(Exception):
    pass


def menu():
    """[(number, mod id, Russian title, one line about it)] in a fixed order."""
    out = []
    for i, n in enumerate(build_mods.load_order(), 1):
        spec = build_mods.load_spec(n)
        about = spec.get("workshop", {}).get("tag_ru") or spec.get("tag_ru") or spec.get("about", {}).get("ru", [""])[0]
        out.append((i, n, spec.get("title_ru") or spec["title"], about))
    return out


def title_ru(name):
    spec = build_mods.load_spec(name)
    return spec.get("title_ru") or spec["title"]


def parse_numbers(text, items):
    """'1 3,5' -> mod ids; raises CombineError on a bad number."""
    by_no = {str(i): n for i, n, _t, _a in items}
    out = []
    for tok in text.replace(",", " ").split():
        if tok not in by_no:
            raise CombineError("нет мода с номером %s" % tok)
        if by_no[tok] not in out:
            out.append(by_no[tok])
    return out


def resolve(names, choose):
    """Drop one mod of every conflicting pair: choose(a, b, what) returns the one to KEEP.
    Returns the final list in the given order."""
    names = list(names)
    while True:
        clash = build_mods.conflicts(names)
        if not clash:
            return names
        a, b, what = clash[0]
        keep = choose(a, b, what)
        if keep not in (a, b):
            raise CombineError("надо выбрать %s или %s" % (a, b))
        names.remove(b if keep == a else a)


def plain(what):
    """'TruckData/Motor Torque, TruckData/Motor/Gear AngVel' -> words a player knows."""
    words = []
    if "Torque" in what:
        words.append("момент мотора")
    if "AngVel" in what:
        words.append("скорости передач")
    return ", ".join(words) or what


def refuse(a, b, what):
    raise CombineError("«%s» и «%s» меняют одно и то же (%s): выберите один из них"
                       % (title_ru(a), title_ru(b), plain(what)))


def ask_choice(a, b, what):
    print()
    print("«%s» и «%s» меняют одно и то же (%s)." % (title_ru(a), title_ru(b), plain(what)))
    print("Вместе их собрать нельзя: одно перезаписало бы другое. Что оставить?")
    print("  1 - %s" % title_ru(a))
    print("  2 - %s" % title_ru(b))
    while True:
        x = input("Номер (1 или 2): ").strip()
        if x in ("1", "2"):
            return a if x == "1" else b


def build(names, out=OUT, game=build_mods.DEFAULT_GAME, verbose=True):
    """Build the one package. Returns its path."""
    if not names:
        raise CombineError("не выбран ни один мод")
    res = build_mods.build_all(game, out, only=names, verbose=False)
    b = res["custom"]
    if verbose:
        trucks = sum(1 for p in b.files if p.startswith("classes/trucks/otc_") and p.endswith(".xml"))
        print("Собрано: %s" % b.zip_path)
        print("  моды: %s" % ", ".join(title_ru(n) for n in names))
        if trucks:
            print("  грузовиков «... (%s)»: %d" % (build_mods.CUSTOM_SUFFIX_RU, trucks))
        if b.levels:
            print("  карт с открытыми грузовиками: %d" % len(b.levels))
    return b.zip_path


def install(extra=()):
    r = subprocess.run([sys.executable, INSTALL] + list(extra))
    return r.returncode


def yes(prompt):
    return input(prompt).strip().lower() in ("д", "да", "y", "yes", "l")


def interactive():
    items = menu()
    print("Свой мод OpenTrail для MudRunner: несколько модов в ОДНОЙ копии каждого грузовика.")
    print("В игре грузовики будут называться «<грузовик> (%s)»." % build_mods.CUSTOM_SUFFIX_RU)
    print()
    for i, _n, t, about in items:
        print("  %d. %s%s" % (i, t, (" - " + about) if about else ""))
    print()
    print("  0. Убрать все моды OpenTrail из игры (откат)")
    print()
    while True:
        text = input("Номера модов через пробел (например 6 2 5), Enter - выход: ").strip()
        if not text:
            return 0
        if text == "0":
            return install(["--remove", "--apply"])
        try:
            names = parse_numbers(text, items)
            break
        except CombineError as e:
            print("Ошибка:", e)
    names = resolve(names, ask_choice)
    print()
    print("Собираю (это может занять минуту)...")
    build(names)
    print()
    if yes("Установить в игру сейчас? Игра должна быть закрыта. (д/н): "):
        code = install(["--custom", "--apply"])
        if code == 0:
            print("Готово. Откат: снова запустите этот файл и выберите 0.")
        return code
    print("Не установлено. Установить потом: python tools/install_local.py --custom --apply")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mods", help="comma separated mod ids (see --list)")
    ap.add_argument("--install", action="store_true", help="install right after the build (game closed)")
    ap.add_argument("--remove", action="store_true", help="take every OpenTrail package out of Config.xml")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--game", default=build_mods.DEFAULT_GAME)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    if a.list:
        for i, n, t, about in menu():
            print("%d. %s - %s (%s)" % (i, n, t, about))
        return 0
    if a.remove:
        return install(["--remove", "--apply"])
    if not a.mods:
        return interactive()
    order = build_mods.load_order()
    names = [x.strip() for x in a.mods.split(",") if x.strip()]
    unknown = [n for n in names if n not in order]
    if unknown:
        raise CombineError("unknown mods: %s (known: %s)" % (", ".join(unknown), ", ".join(order)))
    names = resolve(names, refuse)
    build(names, a.out, a.game)
    if a.install:
        return install(["--custom", "--apply"] + ([] if a.out == OUT else ["--custom-dir", a.out]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CombineError, build_mods.BuildError) as e:
        print("НЕ СОБРАНО:", e)
        sys.exit(2)
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(1)
