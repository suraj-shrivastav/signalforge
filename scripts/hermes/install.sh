#!/bin/bash
# Install the SignalForge scheduler on macOS. Run from anywhere: scripts/hermes/install.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/bin" "$HOME/Library/LaunchAgents"
cp "$here/signalforge_cron_pipeline.sh" "$here/signalforge_cron_tick.sh" "$HOME/bin/"
chmod +x "$HOME/bin/signalforge_cron_"*.sh
if [ ! -f "$HOME/.signalforge.env" ]; then
  cp "$here/signalforge.env.example" "$HOME/.signalforge.env"
  chmod 600 "$HOME/.signalforge.env"
  echo "Edit ~/.signalforge.env and set the real keys, then re-run this script."; exit 0
fi
sed "s#__HOME__#$HOME#g" "$here/ai.signalforge.cron.plist.template" > "$HOME/Library/LaunchAgents/ai.signalforge.cron.plist"
launchctl bootout "gui/$(id -u)/ai.signalforge.cron" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/ai.signalforge.cron.plist"
echo "Installed. Log: $HOME/signalforge-cron.log"
