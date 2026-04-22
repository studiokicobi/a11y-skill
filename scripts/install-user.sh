#!/usr/bin/env bash
# Install the a11y-audit skill at the user level for Claude Code.
# Usage:
#   ./scripts/install-user.sh              # symlink (default)
#   ./scripts/install-user.sh --copy       # copy a snapshot instead
#   ./scripts/install-user.sh --uninstall
#   ./scripts/install-user.sh --force      # replace an existing install without prompting

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$REPO_ROOT/.agents/skills/a11y-audit"
TARGET="$HOME/.claude/skills/a11y-audit"

mode="symlink"
force=0
for arg in "$@"; do
  case "$arg" in
    --copy)      mode="copy" ;;
    --symlink)   mode="symlink" ;;
    --uninstall) mode="uninstall" ;;
    --force)     force=1 ;;
    -h|--help)   sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)           echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

[[ -d "$SOURCE" ]] || { echo "source not found: $SOURCE" >&2; exit 1; }
mkdir -p "$(dirname "$TARGET")"

if [[ -e "$TARGET" || -L "$TARGET" ]]; then
  if [[ $force -eq 0 && "$mode" != "uninstall" ]]; then
    read -rp "$TARGET exists. Replace? [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]] || { echo "aborted"; exit 1; }
  fi
  rm -rf "$TARGET"
fi

case "$mode" in
  uninstall) echo "uninstalled $TARGET" ;;
  symlink)   ln -s "$SOURCE" "$TARGET" && echo "symlinked $TARGET -> $SOURCE" ;;
  copy)      cp -R "$SOURCE" "$TARGET" && echo "copied $SOURCE -> $TARGET" ;;
esac

[[ "$mode" != "uninstall" && -f "$TARGET/SKILL.md" ]] && echo "verified SKILL.md is present."
