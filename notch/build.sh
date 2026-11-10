#!/bin/sh
# Compila em release e monta "Quilate.app" nesta pasta, assinado ad hoc.
set -e
cd "$(dirname "$0")"

swift build -c release

APP="Quilate.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp .build/release/QuilateNotch "$APP/Contents/MacOS/"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>QuilateNotch</string>
    <key>CFBundleIdentifier</key><string>io.github.trivixlabs.quilate</string>
    <key>CFBundleName</key><string>Quilate</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>LSMinimumSystemVersion</key><string>15.0</string>
    <!-- Sem ícone no Dock e sem menu: o app vive só no notch. -->
    <key>LSUIElement</key><true/>
    <!-- App em português: textos do sistema (menus, botões) saem em pt-BR. -->
    <key>CFBundleDevelopmentRegion</key><string>pt-BR</string>
    <key>CFBundleLocalizations</key><array><string>pt-BR</string></array>
</dict>
</plist>
PLIST

# Assinatura ad hoc: roda neste Mac. Para outro Mac precisa de conta Apple Developer.
codesign --force --sign - "$APP"
echo "Pronto: $APP"
