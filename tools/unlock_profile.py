"""Open MudRunner maps by editing the profile UserProfile.stu (tools/profile_stu.py has the format).

Without arguments: a Russian menu (the "Открыть карты MudRunner.bat" file starts it).
  --maps       open every map: profile.numLogPoints = the biggest need in the exe table
  --restore    put back the profile from the newest backup this tool made
  --write      actually write (without it: only show what would change)
  --yes        do not ask "write? (да/нет)" (tests)
Always: the game must be closed, a backup UserProfile.stu.opentrail-<time> is made before
writing, the written file is parsed again and compared field by field before it replaces
the profile.
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

DEFAULT_PROFILE = os.path.join(os.environ.get("APPDATA", ""), "SpinTires MudRunner", "UserProfile.stu")
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


def make_backup(path):
    dst = path + BACKUP_MARK + time.strftime("%Y%m%d-%H%M%S")
    n = 1
    while os.path.exists(dst):
        n += 1
        dst = path + BACKUP_MARK + time.strftime("%Y%m%d-%H%M%S") + "-%d" % n
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


MENU = """Открыть карты MudRunner (правка профиля UserProfile.stu)
Игра должна быть закрыта. Перед записью делается резервная копия.

  1 - открыть все карты (сначала покажу, что изменится)
  2 - открыть гаражи на карте
  3 - открыть все грузовики в профиле
  4 - откат: вернуть профиль из последней резервной копии
  0 - выход"""

NOT_YET = {
    "2": "Гаражи пока не открываю. Замок гаража - очки гаража в сохранении карты (*.sts в "
         "UserSaves), а не в профиле. Формат сохранения ещё не разобран до конца, поэтому "
         "менять его вслепую не буду.",
    "3": "Грузовики пока не открываю. В профиле у каждого сохранения список открытых грузовиков - "
         "это их координаты на карте (3 числа на грузовик), а как игра сверяет их с грузовиками "
         "карты, ещё не проверено по коду игры. Менять вслепую не буду.",
}


def menu(profile, exe):
    say(MENU)
    try:
        choice = input("Ваш выбор: ").strip()
    except EOFError:
        return 0
    if choice == "1":
        return run("maps", profile, exe, True, False)   # shows the changes, then asks
    if choice == "4":
        return run("restore", profile, exe, True, False)
    if choice in NOT_YET:
        say(NOT_YET[choice])
        return 0
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--exe", default=os.path.join(install_local.build_mods.DEFAULT_GAME, "MudRunner.exe"))
    ap.add_argument("--maps", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    if not a.maps and not a.restore:
        return menu(a.profile, a.exe)
    return run("restore" if a.restore else "maps", a.profile, a.exe, a.write, a.yes)


if __name__ == "__main__":
    sys.exit(main())
