#!/bin/sh
# Gera e carrega o LaunchAgent que sobe `quilate servir` no login do Mac.
# Uso: sh ops/instalar-launchd.sh        (instala ou reinstala)
#      sh ops/instalar-launchd.sh remover
set -eu

LABEL="io.github.trivixlabs.quilate"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UV="$(command -v uv)"
LOGS="$HOME/quilate-dados/logs"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "remover" ]; then
  rm -f "$PLIST"
  echo "LaunchAgent removido."
  exit 0
fi

mkdir -p "$LOGS" "$HOME/Library/LaunchAgents"
cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$UV</string><string>run</string><string>quilate</string><string>servir</string></array>
  <key>WorkingDirectory</key><string>$REPO/backend</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$(dirname "$UV"):/opt/homebrew/bin:/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOGS/quilate.log</string>
  <key>StandardErrorPath</key><string>$LOGS/quilate.log</string>
</dict>
</plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "LaunchAgent $LABEL carregado. Log em $LOGS/quilate.log"
