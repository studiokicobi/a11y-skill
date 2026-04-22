#!/usr/bin/env bash
# pack.sh — build a distributable a11y-audit.skill archive from the unpacked tree.
#
# Usage:
#   scripts/pack.sh                   # writes dist/a11y-audit.skill
#   scripts/pack.sh path/to/out.skill # writes to a custom path
#
# The unpacked skill at .agents/skills/a11y-audit/ is the editable source of truth
# (see decisions/0001-unpacked-skill-tree-is-source-of-truth.md). The archive is
# a distribution artifact and is not checked in; run this script on demand when
# you need one to upload to Claude.ai or attach to a release.

set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
src="${repo_root}/.agents/skills/a11y-audit"
out="${1:-${repo_root}/dist/a11y-audit.skill}"

if [ ! -d "${src}" ]; then
  echo "pack.sh: skill tree not found at ${src}" >&2
  exit 1
fi

mkdir -p "$(dirname -- "${out}")"
rm -f "${out}"

# Zip with the archive's top-level directory named "a11y-audit/", matching the
# layout expected by Claude.ai, Claude Code, and Codex skill installers.
staging="$(mktemp -d)"
trap 'rm -rf "${staging}"' EXIT
cp -R "${src}" "${staging}/a11y-audit"
# Strip local dev artifacts that shouldn't ship.
rm -rf "${staging}/a11y-audit/.a11y-audit-deps" \
       "${staging}/a11y-audit/scripts/__pycache__" \
       "${staging}/a11y-audit/fixtures"

(cd "${staging}" && zip -qr "${out}" a11y-audit)

echo "Packed: ${out}"
