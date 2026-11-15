#!/usr/bin/env bash
# Build the Hermes skill ~/.hermes/skills/signalforge-pipeline/SKILL.md from three repo files:
# skill-header.md (frontmatter and role), signalforge-reference.md and telegram-control.md
# (each without its first four lines). Backs up the old skill to SKILL.md.bak. Run it again
# whenever any of the three files changes; Hermes must never write the skill itself.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="${HERMES_HOME:-$HOME/.hermes}/skills/signalforge-pipeline/SKILL.md"
mkdir -p "$(dirname "$dest")"
if [ -f "$dest" ]; then cp "$dest" "$dest.bak"; fi
{
  cat "$here/skill-header.md"
  echo
  sed 1,4d "$here/signalforge-reference.md"
  echo
  echo "# Owner commands (Telegram)"
  echo
  sed 1,4d "$here/telegram-control.md"
} > "$dest.tmp"
mv "$dest.tmp" "$dest"
echo "wrote $dest"
