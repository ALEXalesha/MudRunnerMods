"""Open MudRunner maps by editing the profile UserProfile.stu (tools/profile_stu.py has the format),
and the trucks and garages of one map save UserSaves/<name>.sts (tools/save_sts.py).

Without arguments: a Russian menu (the "Открыть карты MudRunner.bat" file starts it).
  --maps          open every map: profile.numLogPoints = the biggest need in the exe table
  --restore       put back the profile from the newest backup this tool made
  --trucks        open every truck in a map save (isUnlocked = 1)
  --garages       open every garage in a map save (garage points = the need, 4)
  --restore-save  put back a map save from the newest backup this tool made of it
  --save NAME     which save (file name or path; default: the last played map of the profile)
  --write         actually write (without it: only show what would change)
  --yes           do not ask "write? (да/нет)" (tests)
Always: the game must be closed, a backup is made before writing (the profile next to it as
UserProfile.stu.opentrail-<time>; a save into SAVE_BACKUP_DIR, outside the folders the game
and Steam Cloud use), the written file is parsed again and only the intended bytes may differ.
"""
import argparse
import glob
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_limits  # noqa: E402
import install_local  # noqa: E402
import profile_stu  # noqa: E402
import save_sts  # noqa: E402

DEFAULT_PROFILE = os.path.join(os.environ.get("APPDATA", ""), "SpinTires MudRunner", "UserProfile.stu")
SAVE_BACKUP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "OpenTrail",
                               "MudRunner saves backup")
BACKUP_MARK = ".opentrail-"
MAP_NAMES_RU = {"level_plains": "Болото (Plains)", "level_volcano": "Вулкан (Volcano)",
                "level_coast": "Побережье (Coast)", "level_river": "Река (River)",
                "level_hill": "Холм (Hill)", "level_flood": "Наводнение (Flood)",
                "level_valley": "Долина (Valley)", "level_ridge": "Хребет (Ridge)",
                "level_dlc3_01": "DLC 3, карта 1", "level_dlc3_02": "DLC 3, карта 2",
                "level_dlc4_01": "DLC 4 (Old-timers)"}


def say(text=""):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def requirements(exe):
    if exe and os.path.isfile(exe):
        got = engine_limits.read_exe_map_requirements(exe)
        if got:
            return got
    return dict(engine_limits.MAP_LOG_POINTS)


def plan_maps(data, need):
    """(new bytes, list of Russian lines) - what --maps changes."""
    prof = profile_stu.parse(data)
    target = max([prof["numLogPoints"]] + list(need.values()))
    locked = profile_stu.locked_maps(prof, need)
    lines = ["Очки прогресса карт сейчас: %d, нужно для всех карт: %d." % (prof["numLogPoints"], target),
             "Карты, которым очков не хватает (пройденные карты игра и так держит открытыми):"]
    if not locked:
        lines.append("Все карты уже открыты, менять нечего.")
        return data, lines
    for name in locked:
        lines.append("  будет открыта: %s (нужно очков: %d)" % (MAP_NAMES_RU.get(name, name), need[name]))
    return profile_stu.set_log_points(data, target), lines


def check_same_except(old, new, allowed):
    """The written file parses and only the allowed top-level fields differ."""
    a = profile_stu.parse(old)
    b = profile_stu.parse(new)
    skip = {"numLogPoints_at"}
    for k in set(a) | set(b):
        if k in skip or k in allowed:
            continue
        if a.get(k) != b.get(k):
            raise profile_stu.StuError("field %s changed unexpectedly" % k)


def backups(path):
    return sorted(glob.glob(glob.escape(path) + BACKUP_MARK + "*"))


def make_backup(path, folder=None):
    """Copy path to <folder or its own folder>/<name>.opentrail-<time>; returns the copy."""
    if folder:
        os.makedirs(folder, exist_ok=True)
        path_in = os.path.join(folder, os.path.basename(path))
    else:
        path_in = path
    dst = path_in + BACKUP_MARK + time.strftime("%Y%m%d-%H%M%S")
    n = 1
    while os.path.exists(dst):
        n += 1
        dst = path_in + BACKUP_MARK + time.strftime("%Y%m%d-%H%M%S") + "-%d" % n
    shutil.copy2(path, dst)
    return dst


def write_atomic(path, data):
    tmp = path + ".opentrail-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def ask_yes(question, assume_yes):
    if assume_yes:
        return True
    try:
        ans = input(question + " (да/нет): ").strip().lower()
    except EOFError:
        return False
    return ans in ("да", "д", "yes", "y")


def run(action, profile, exe, write, assume_yes):
    """0 = done (or nothing to do), 1 = refused / error. Prints Russian text."""
    if install_local.game_running():
        say("Игра MudRunner запущена. Закройте её и запустите этот файл снова.")
        return 1
    if not os.path.isfile(profile):
        say("Не найден профиль: %s" % profile)
        return 1
    with open(profile, "rb") as f:
        data = f.read()
    if action == "restore":
        bks = backups(profile)
        if not bks:
            say("Резервных копий нет - откатывать нечего.")
            return 1
        src = bks[-1]
        with open(src, "rb") as f:
            back = f.read()
        profile_stu.parse(back)
        say("Будет возвращён профиль из копии %s." % os.path.basename(src))
        if not write:
            say("Пробный режим: ничего не записано.")
            return 0
        if not ask_yes("Вернуть профиль из копии?", assume_yes):
            say("Отменено, ничего не записано.")
            return 1
        make_backup(profile)
        write_atomic(profile, back)
        say("Готово: профиль возвращён.")
        return 0
    try:
        new, lines = plan_maps(data, requirements(exe))
    except profile_stu.StuError as e:
        say("Профиль не удалось разобрать (%s). Ничего не меняю." % e)
        return 1
    for line in lines:
        say(line)
    if new == data:
        return 0
    check_same_except(data, new, {"numLogPoints"})
    if not write:
        say("Пробный режим: ничего не записано.")
        return 0
    if not ask_yes("Записать изменения в профиль?", assume_yes):
        say("Отменено, ничего не записано.")
        return 1
    bk = make_backup(profile)
    write_atomic(profile, new)
    with open(profile, "rb") as f:
        check_same_except(data, f.read(), {"numLogPoints"})
    say("Готово. Резервная копия: %s" % os.path.basename(bk))
    say("Откат: снова запустите файл и выберите пункт отката.")
    return 0


# --------------------------------------------------------------------------- map saves (*.sts)

def default_saves_dir(profile):
    return os.path.join(os.path.dirname(os.path.abspath(profile)), "UserSaves")


def level_of_save(path):
    """The game level a save belongs to (level_<x>.sts), or None (Workshop and other maps)."""
    name = os.path.basename(path).lower()
    if name.startswith("level_") and name.endswith(".sts"):
        return name[:-4]
    return None


def level_garages(game_dir, level):
    """[(x, z)] of the level's garage locators (type 1) from the game files, or None."""
    try:
        fs = install_local.build_mods.mrxml.GameFs(game_dir)
        path = "levels/%s.stg" % level
        if not fs.exists(path):
            return None
        with fs.open(path) as fh:
            head = fh.read(install_local.build_mods.STG_HEAD)
        recs, end = install_local.build_mods.read_stg_trucks(head)
        info = install_local.build_mods.read_stg_locators(head, end)
    except Exception:          # no game, a broken archive: no garages known
        return None
    return [(l["x"], l["z"]) for l in info["locators"] if l["type"] == install_local.build_mods.GARAGE_LOCATOR]


def truck_names(game_dir):
    """{truck id: name the game shows} from strings/ru/*.txt of the game ({} without the game)."""
    out = {}
    try:
        fs = install_local.build_mods.mrxml.GameFs(game_dir)
        for path in fs.list("strings/ru/", ".txt"):
            with fs.open(path) as fh:
                raw = fh.read()
            text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
            lines = [x.strip() for x in text.splitlines()]
            for i, line in enumerate(lines[:-1]):
                if line.startswith("/") and lines[i + 1] and not lines[i + 1].startswith("/"):
                    out.setdefault(line[1:], lines[i + 1])
    except Exception:
        return {}
    return out


def garage_need(exe):
    if exe and os.path.isfile(exe):
        got = engine_limits.read_exe_garage_rules(exe)
        if got:
            return got[0][0]
    return engine_limits.GARAGE_NEED[0]


def list_saves(profile, saves_dir):
    """[(path, Russian label)] of the map saves, the last played map first, then the newest."""
    played = {}
    last = None
    try:
        with open(profile, "rb") as f:
            prof = profile_stu.parse(f.read())
        last = prof["strLevelLast"]
        played = {m["strId"]: m["strLastPlayed"] for m in prof["maps"]}
    except (OSError, profile_stu.StuError):
        pass
    def when(p):
        try:          # the profile's "MM/DD/YY HH:MM"; the file time when it has none
            return time.mktime(time.strptime(played.get(os.path.basename(p)[:-4], ""), "%m/%d/%y %H:%M"))
        except (ValueError, OverflowError):
            return os.path.getmtime(p)

    paths = glob.glob(os.path.join(glob.escape(saves_dir), "*.sts"))
    paths.sort(key=lambda p: (os.path.basename(p)[:-4] != last, -when(p)))
    out = []
    for p in paths:
        sid = os.path.basename(p)[:-4]
        label = MAP_NAMES_RU.get(sid, "сохранение %s (карта из Мастерской или не из игры)" % sid)
        if played.get(sid):
            try:
                shown = time.strftime("%d.%m.%y %H:%M", time.strptime(played[sid], "%m/%d/%y %H:%M"))
            except ValueError:
                shown = played[sid]
            label += ", игра от %s" % shown
        out.append((p, label))
    return out


def describe_truck(t, names):
    shown = names.get(t["type"], t["type"])
    text = shown if shown == t["type"] else "%s (%s)" % (shown, t["type"])
    if t["addons"]:
        text += " + " + ", ".join(names.get(a, a) for a in t["addons"])
    return "%s, место (%d, %d)" % (text, round(t["x"]), round(t["z"]))


def plan_save(action, data, path, game_dir, exe):
    """(new bytes, Russian lines, offsets that may change). Raises save_sts.StsError."""
    if action == "trucks":
        new, locked = save_sts.unlock_trucks(data)
        ts = save_sts.trucks(data)
        names = truck_names(game_dir)
        lines = ["Грузовиков и прицепов в сохранении: %d, заперто: %d." % (len(ts), len(locked))]
        if not locked:
            lines.append("Все грузовики уже открыты, менять нечего.")
        for t in locked:
            lines.append("  будет открыт: " + describe_truck(t, names))
        return new, lines, {t["unlocked_at"] for t in locked}
    level = level_of_save(path)
    if not level:
        raise save_sts.StsError("это сохранение не карты из игры (Мастерская или другое), "
                                "где у неё гаражи, по файлам игры не узнать")
    gxz = level_garages(game_dir, level)
    if gxz is None:
        raise save_sts.StsError("не нашёл файл карты %s в игре" % level)
    need = garage_need(exe)
    new, low = save_sts.open_garages(data, gxz, need)
    lines = ["Гаражей на карте: %d, нужно очков гаража для открытия: %d." % (len(gxz), need)]
    if not low:
        lines.append("Все гаражи уже открыты, менять нечего.")
    for g in low:
        lines.append("  будет открыт гараж у точки (%d, %d): очков было %d, станет %d"
                     % (round(g["x"]), round(g["z"]), g["points"], need))
    allowed = set()
    for g in low:
        allowed.update(range(g["points_at"], g["points_at"] + 4))
    return new, lines, allowed


def save_backups(path, backup_dir):
    return sorted(glob.glob(os.path.join(glob.escape(backup_dir), glob.escape(os.path.basename(path)))
                            + BACKUP_MARK + "*"))


def run_save(action, path, game_dir, exe, write, assume_yes, backup_dir=None):
    """Like run(), for one map save. 0 = done (or nothing to do), 1 = refused / error."""
    backup_dir = backup_dir or SAVE_BACKUP_DIR
    if install_local.game_running():
        say("Игра MudRunner запущена. Закройте её и запустите этот файл снова.")
        return 1
    if not path or not os.path.isfile(path):
        say("Не найдено сохранение карты: %s" % path)
        return 1
    with open(path, "rb") as f:
        data = f.read()
    if action == "restore":
        bks = save_backups(path, backup_dir)
        if not bks:
            say("Резервных копий этого сохранения нет - откатывать нечего.")
            return 1
        with open(bks[-1], "rb") as f:
            back = f.read()
        try:
            save_sts.trucks(back)
        except save_sts.StsError as e:
            say("Резервная копия %s не разбирается (%s). Ничего не меняю." % (os.path.basename(bks[-1]), e))
            return 1
        say("Будет возвращено сохранение из копии %s." % os.path.basename(bks[-1]))
        if not write:
            say("Пробный режим: ничего не записано.")
            return 0
        if not ask_yes("Вернуть сохранение из копии?", assume_yes):
            say("Отменено, ничего не записано.")
            return 1
        make_backup(path, backup_dir)
        write_atomic(path, back)
        say("Готово: сохранение возвращено.")
        return 0
    try:
        new, lines, allowed = plan_save(action, data, path, game_dir, exe)
    except save_sts.StsError as e:
        say("Сохранение не удалось разобрать: %s. Ничего не меняю." % e)
        return 1
    for line in lines:
        say(line)
    if new == data:
        return 0
    if not set(save_sts.changed_offsets(data, new)) <= allowed:
        say("Изменилось бы больше, чем нужно. Ничего не меняю.")
        return 1
    if not write:
        say("Пробный режим: ничего не записано.")
        return 0
    if not ask_yes("Записать изменения в сохранение карты?", assume_yes):
        say("Отменено, ничего не записано.")
        return 1
    bk = make_backup(path, backup_dir)
    write_atomic(path, new)
    with open(path, "rb") as f:
        written = f.read()
    if written != new:
        say("Записанный файл не совпал с задуманным. Верните копию пунктом отката: %s" % bk)
        return 1
    save_sts.trucks(written)
    say("Готово. Резервная копия: %s" % bk)
    say("Откат: снова запустите файл и выберите пункт 5.")
    return 0


MENU = """Открыть карты MudRunner (правка профиля и сохранений карт)
Игра должна быть закрыта. Перед записью делается резервная копия.

  1 - открыть все карты (сначала покажу, что изменится)
  2 - открыть гаражи на карте (в сохранении карты)
  3 - открыть грузовики на карте (в сохранении карты)
  4 - откат: вернуть профиль из последней резервной копии
  5 - откат: вернуть сохранение карты из последней резервной копии
  0 - выход"""

SAVE_HINT = ("Грузовики и гаражи открываются в сохранении карты. Сначала начните игру на карте, "
             "выйдите в главное меню (игра сохранит карту) и закройте игру.")


def choose_save(profile, saves_dir):
    saves = list_saves(profile, saves_dir)
    if not saves:
        say("Сохранений карт нет (%s). %s" % (saves_dir, SAVE_HINT))
        return None
    say("Сохранения карт:")
    for i, (_p, label) in enumerate(saves, 1):
        say("  %d - %s" % (i, label))
    try:
        ans = input("Номер сохранения (Enter - первое): ").strip()
    except EOFError:
        return None
    if not ans:
        return saves[0][0]
    if ans.isdigit() and 1 <= int(ans) <= len(saves):
        return saves[int(ans) - 1][0]
    say("Нет такого номера.")
    return None


def menu(profile, exe, game_dir=None, saves_dir=None, backup_dir=None):
    say(MENU)
    try:
        choice = input("Ваш выбор: ").strip()
    except EOFError:
        return 0
    if choice == "1":
        return run("maps", profile, exe, True, False)   # shows the changes, then asks
    if choice == "4":
        return run("restore", profile, exe, True, False)
    if choice in ("2", "3", "5"):
        say(SAVE_HINT)
        path = choose_save(profile, saves_dir or default_saves_dir(profile))
        if not path:
            return 0
        action = {"2": "garages", "3": "trucks", "5": "restore"}[choice]
        return run_save(action, path, game_dir or install_local.build_mods.DEFAULT_GAME, exe, True, False,
                        backup_dir)
    return 0


def resolve_save(arg, profile, saves_dir):
    if arg:
        if os.path.isfile(arg):
            return arg
        name = arg if arg.lower().endswith(".sts") else arg + ".sts"
        return os.path.join(saves_dir, name)
    saves = list_saves(profile, saves_dir)
    return saves[0][0] if saves else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--exe", default=os.path.join(install_local.build_mods.DEFAULT_GAME, "MudRunner.exe"))
    ap.add_argument("--game", default=install_local.build_mods.DEFAULT_GAME)
    ap.add_argument("--saves-dir", help="folder of the map saves (default: UserSaves next to the profile)")
    ap.add_argument("--backup-dir", default=SAVE_BACKUP_DIR, help="where save backups go")
    ap.add_argument("--save", help="map save: file name in the saves folder (level_volcano) or a path")
    ap.add_argument("--maps", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--trucks", action="store_true")
    ap.add_argument("--garages", action="store_true")
    ap.add_argument("--restore-save", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    saves_dir = a.saves_dir or default_saves_dir(a.profile)
    save_action = "trucks" if a.trucks else "garages" if a.garages else "restore" if a.restore_save else None
    if save_action:
        path = resolve_save(a.save, a.profile, saves_dir)
        return run_save(save_action, path, a.game, a.exe, a.write, a.yes, a.backup_dir)
    if not a.maps and not a.restore:
        return menu(a.profile, a.exe, a.game, saves_dir, a.backup_dir)
    return run("restore" if a.restore else "maps", a.profile, a.exe, a.write, a.yes)


if __name__ == "__main__":
    sys.exit(main())
