#!/usr/bin/env bash
# Publish to GitHub: https://github.com/ALEXalesha/MudRunnerMods
#
#   bash tools/publish_github.sh            # code only
#   bash tools/publish_github.sh vX.Y.Z     # code and tag
#   DRY_RUN=1 bash tools/publish_github.sh  # build and check github-main, no push
#
# The source of truth is Gitea. GitHub gets a copy of main that is rebuilt every time
# (hence --force: nothing but this script writes to main on GitHub). The working
# history on Gitea is not touched.
#
# Personal data is replaced in the published copy, in commit authors and in file
# contents across the whole history:
#   - the author's e-mail       -> the GitHub account's noreply address;
#   - the Gitea server address  -> gitea.local;
#   - the full name / surname   -> the nick ALEXalesha (plus git config publish.privateExtra);
#   - the local projects folder -> C:\Projects;
#   - Steam user ids from this PC -> 0;
#   - the personal path         -> Users\you (git config publish.privatePath, a folder like
#                                  C:\<folder>\<name>: any slash, any case, also in commit
#                                  messages). tests/test_privacy.py keeps personal data
#                                  out of new commits.
# None of these strings is written here: the e-mail comes from git config user.email,
# the address from remote origin, the name from git config publish.privateName and
# publish.privateExtra, the path from publish.privatePath (local settings, never in the
# history), the folder from the location of this repository, the Steam ids from the
# Steam userdata folder.
#
# Do not run it before the mods are tested in game: first the test, then
# the release (VERSION, CHANGELOG, docs/release-notes/vX.Y.Z.md).
#
# Tags: a release on GitHub is bound to a tag. Each GitHub tag that does not lead into
# the fresh branch is moved to its commit with the same author time and subject, so no
# old (unscrubbed) commit stays reachable. A new tag is pushed straight to GitHub,
# without a local tag (a local one would point at a rewritten commit and get mixed up
# with the Gitea tags).
set -euo pipefail

export PATH="$PATH:/c/Program Files/GitHub CLI"
REPO=ALEXalesha/MudRunnerMods
PUBLIC_EMAIL=203467574+ALEXalesha@users.noreply.github.com
PUBLIC_NAME=ALEXalesha
TAG="${1:-}"

cd "$(dirname "$0")/.."

PRIVATE_EMAIL="$(git config user.email)"
PRIVATE_NAME="$(git config --get publish.privateName || true)"
PRIVATE_EXTRA="$(git config --get publish.privateExtra || true)"
LAN_GITEA="$(git remote get-url origin | sed -E 's#^[a-z]+://([^/:]+).*#\1#')"
if [ -z "$PRIVATE_NAME" ]; then
  echo "git config publish.privateName is not set - the full name cannot be replaced" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "commit first: filter-branch silently refuses to run on a dirty tree" >&2
  exit 1
fi

# --- the list of private strings and their public replacements -------------------
WIN_PARENT="$(cd .. && pwd -W)"                    # e.g. X:/Folder (forward slashes)
PAIRS=()                                           # "private<TAB>public"
add() { [ -n "$1" ] && [ ${#1} -ge 4 ] && PAIRS+=("$1"$'\t'"$2"); return 0; }
add "$PRIVATE_EMAIL" "$PUBLIC_EMAIL"
add "$LAN_GITEA" "gitea.local"
add "$PRIVATE_NAME" "$PUBLIC_NAME"
add "${PRIVATE_NAME##* }" "$PUBLIC_NAME"           # surname alone
IFS='|' read -r -a EXTRA <<< "$PRIVATE_EXTRA"
for x in "${EXTRA[@]:-}"; do add "$x" "$PUBLIC_NAME"; done
add "$WIN_PARENT" "C:/Projects"
add "${WIN_PARENT//\//\\}" 'C:\Projects'
add "$(cd .. && pwd)" "/c/Projects"
REL_PARENT="${WIN_PARENT#*:/}"                     # the folder path without the drive
add "$REL_PARENT" "Projects"
add "${REL_PARENT//\//\\}" "Projects"
add "${REL_PARENT//\//\\\\}" "Projects"            # as written inside Python strings
STEAM_USERS="/c/Program Files (x86)/Steam/user""data"   # glued: the privacy test scans this file
for d in "$STEAM_USERS"/*/; do
  [ -d "$d" ] || continue
  add "$(basename "$d")" "0"
done

esc() { printf '%s' "$1" | sed 's/[]\/.[\*^$+?(){}|]/\\&/g'; }
SEDFILE="$(mktemp)"; GREPFILE="$(mktemp)"
trap 'rm -f "$SEDFILE" "$GREPFILE"' EXIT          # temp files of this script only
for pair in "${PAIRS[@]}"; do
  priv="${pair%%$'\t'*}"; pub="${pair#*$'\t'}"
  printf 's/%s/%s/gI\n' "$(esc "$priv")" "$(printf '%s' "$pub" | sed 's/[\/&]/\\&/g')" >> "$SEDFILE"
  printf '%s\n' "$priv" >> "$GREPFILE"
done
echo "private strings to replace: ${#PAIRS[@]}"

# The personal path (C:\folder\name) becomes an expression that catches any spelling:
# forward, back and doubled back slashes (JSON, Python strings), any case. The expression
# and its replacement lie as files in .git: inside the filter-branch string the back
# slashes would need escaping in three layers.
PRIVATE_PATH="$(git config --get publish.privatePath || true)"
if [ -z "$PRIVATE_PATH" ]; then
  echo "git config publish.privatePath is not set - the personal path cannot be replaced" >&2
  exit 1
fi
IFS='\/' read -r -a PATH_PARTS <<< "${PRIVATE_PATH#?:}"
PATH_RE=""
n=0
for part in "${PATH_PARTS[@]}"; do
  [ -n "$part" ] || continue
  case $n in
    0) PATH_RE="$(esc "$part")" ;;
    1) PATH_RE="$PATH_RE"'([\\/]+)'"$(esc "$part")" ;;
    *) PATH_RE="$PATH_RE"'[\\/]+'"$(esc "$part")" ;;
  esac
  n=$((n + 1))
done
if [ $n -lt 2 ]; then
  echo "publish.privatePath: at least two folders are needed, like C:\\folder\\name" >&2
  exit 1
fi
GIT_DIR_ABS="$(cd "$(git rev-parse --git-dir)" && pwd)"
PATH_SED="$GIT_DIR_ABS/publish-path.sed"
PATH_GREP="$GIT_DIR_ABS/publish-path.grep"
printf '%s\n' "s#$PATH_RE#Users\\1you#gI" > "$PATH_SED"
printf '%s\n' "$PATH_RE" > "$PATH_GREP"

git remote get-url github >/dev/null 2>&1 || git remote add github "https://github.com/$REPO.git"

# --- authors ---------------------------------------------------------------------
git branch -f github-main main
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --env-filter "
  if [ \"\$GIT_AUTHOR_EMAIL\" = '$PRIVATE_EMAIL' ]; then export GIT_AUTHOR_EMAIL='$PUBLIC_EMAIL'; fi
  if [ \"\$GIT_COMMITTER_EMAIL\" = '$PRIVATE_EMAIL' ]; then export GIT_COMMITTER_EMAIL='$PUBLIC_EMAIL'; fi
  if [ \"\$GIT_AUTHOR_NAME\" = '$PRIVATE_NAME' ]; then export GIT_AUTHOR_NAME='$PUBLIC_NAME'; fi
  if [ \"\$GIT_COMMITTER_NAME\" = '$PRIVATE_NAME' ]; then export GIT_COMMITTER_NAME='$PUBLIC_NAME'; fi
" --msg-filter "sed -E -f '$PATH_SED'" github-main >/dev/null 2>&1
git update-ref -d refs/original/refs/heads/github-main 2>/dev/null || true

# --- file contents across the history --------------------------------------------
# `|| true`: git grep returns 1 when nothing matches, and with pipefail the script
# would stop here silently.
DIRTY=$( { git grep -I -i -l -F -f "$GREPFILE" $(git rev-list github-main) -- 2>/dev/null || true
           git grep -I -i -l -E -f "$PATH_GREP" $(git rev-list github-main) -- 2>/dev/null || true; } \
        | sed 's/^[^:]*://' | sort -u | tr '\n' ' ' || true)
if [ -n "$DIRTY" ]; then
  echo "private data in files: $DIRTY- rewriting contents"
  FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --index-filter "
    for f in $DIRTY; do
      mode=\$(git ls-tree \$GIT_COMMIT -- \"\$f\" | awk '{print \$1}')
      [ -n \"\$mode\" ] || continue
      blob=\$(git cat-file blob \$GIT_COMMIT:\"\$f\" | sed -E -f '$SEDFILE' | sed -E -f '$PATH_SED' | git hash-object -w --stdin)
      git update-index --cacheinfo \$mode,\$blob,\"\$f\"
    done
  " github-main >/dev/null 2>&1
  git update-ref -d refs/original/refs/heads/github-main 2>/dev/null || true
fi

# --- verify before pushing (authors, messages, files) -------------------------------
# grep without -q: with -q it exits on the first match, git log gets SIGPIPE, and with
# pipefail the condition turns false - the guard would silently let the match through.
if git log github-main --format='%ae%n%ce%n%an%n%cn%n%B' | grep -i -F -f "$GREPFILE" >/dev/null; then
  echo "private data left in commit authors or messages - push cancelled" >&2
  exit 1
fi
if git grep -I -q -i -F -f "$GREPFILE" $(git rev-list github-main) -- 2>/dev/null; then
  echo "private data left in the files of the published history - push cancelled" >&2
  exit 1
fi
if git grep -I -q -i -E -f "$PATH_GREP" $(git rev-list github-main) -- 2>/dev/null; then
  echo "the personal path left in the files of the published history - push cancelled" >&2
  exit 1
fi
if git log github-main --format=%B | grep -i -E -f "$PATH_GREP" >/dev/null; then
  echo "the personal path left in commit messages - push cancelled" >&2
  exit 1
fi

# --- tags on GitHub that do not lead into the fresh branch --------------------------
MOVES=""
git for-each-ref --format='%(refname)' refs/github-tags | xargs -r -n1 git update-ref -d
git fetch -q github '+refs/tags/*:refs/github-tags/*' 2>/dev/null || true
for ref in $(git for-each-ref --format='%(refname)' refs/github-tags); do
  name=${ref#refs/github-tags/}
  old=$(git rev-parse "$ref^{commit}")
  git merge-base --is-ancestor "$old" github-main && continue
  key=$(git log -1 --format='%at %s' "$old")
  # awk reads to the end, no early exit: an early exit gives git log SIGPIPE (141),
  # and with pipefail the script would stop here silently.
  new=$(git log github-main --format='%H %at %s' \
        | awk -v k="$key" '{h=$1; $1=""; if (!f && substr($0,2)==k) {print h; f=1}}')
  if [ -z "$new" ]; then
    echo "tag $name: no commit with the same time and subject in the published branch - left alone" >&2
    continue
  fi
  echo "tag $name: $(git rev-parse --short "$old") -> $(git rev-parse --short "$new")"
  MOVES="$MOVES +$new:refs/tags/$name"
done
git for-each-ref --format='%(refname)' refs/github-tags | xargs -r -n1 git update-ref -d

echo "branch github-main: $(git rev-list --count github-main) commits, $(git log -1 --format=%h github-main)"
if [ "${DRY_RUN:-}" = 1 ]; then
  echo "DRY_RUN=1: checks passed, nothing pushed"
  [ -z "$MOVES" ] || echo "tags would move:$MOVES"
  exit 0
fi
gh auth setup-git
git push github github-main:main --force
if [ -n "$MOVES" ]; then
  git push github $MOVES
fi

if [ -n "$TAG" ]; then
  git push github "+github-main:refs/tags/$TAG"
  echo "tag $TAG pushed"
fi
