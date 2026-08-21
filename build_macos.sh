#!/usr/bin/env bash
###############################################################################
# build_macos.sh — сборка standalone .app и .dmg для macOS
#
# Требует: macOS, Python 3.9+, Poetry (или pip)
#
# Использование:
#   ./build_macos.sh            # полная сборка .app + .dmg
#   ./build_macos.sh --app      # только .app
#   ./build_macos.sh --clean    # очистить build/dist
###############################################################################
set -e

APP_NAME="SP-404SX Manager"
DIST_DIR="dist"
BUILD_DIR="build"

# Цвета
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
info(){ echo -e "${G}▶ $1${N}"; }
warn(){ echo -e "${Y}⚠ $1${N}"; }
err(){  echo -e "${R}✖ $1${N}"; }

# ── Проверка платформы ──
if [[ "$(uname)" != "Darwin" ]]; then
    err "Этот скрипт работает только на macOS!"
    exit 1
fi

# ── Очистка ──
if [[ "$1" == "--clean" ]]; then
    info "Очистка build/ и dist/…"
    rm -rf "$BUILD_DIR" "$DIST_DIR" icon.icns icon.iconset icon.png
    info "Готово."
    exit 0
fi

# ── Определяем менеджер (poetry или pip) ──
if command -v poetry &>/dev/null && [[ -f pyproject.toml ]]; then
    RUN="poetry run"
    info "Использую Poetry"
    poetry install --extras analysis
    poetry run pip install py2app pillow
else
    RUN=""
    warn "Poetry не найден — использую системный python"
    pip install py2app pillow PySide6 librosa numpy soundfile
fi

# ── 1. Генерация иконки ──
info "Генерация иконки…"
$RUN python make_icon.py

# icon.png → icon.icns (нужны утилиты macOS: sips, iconutil)
if [[ -f icon.png ]]; then
    info "Конвертация PNG → ICNS…"
    rm -rf icon.iconset
    mkdir -p icon.iconset
    for s in 16 32 64 128 256 512; do
        sips -z $s $s icon.png --out "icon.iconset/icon_${s}x${s}.png" &>/dev/null
        d=$((s*2))
        sips -z $d $d icon.png --out "icon.iconset/icon_${s}x${s}@2x.png" &>/dev/null
    done
    iconutil -c icns icon.iconset -o icon.icns
    rm -rf icon.iconset
    info "icon.icns создан."
fi

# ── 2. Сборка .app через py2app ──
info "Сборка .app (py2app)… это может занять пару минут"
rm -rf "$BUILD_DIR" "$DIST_DIR"
$RUN python setup.py py2app

APP_PATH="$DIST_DIR/$APP_NAME.app"
if [[ ! -d "$APP_PATH" ]]; then
    err "Сборка не удалась — $APP_PATH не найден"
    exit 1
fi
info ".app собран: $APP_PATH"

# Снимаем quarantine-атрибут (для локального запуска)
xattr -cr "$APP_PATH" 2>/dev/null || true

# ── Только .app? ──
if [[ "$1" == "--app" ]]; then
    info "Готово! Приложение: $APP_PATH"
    exit 0
fi

# ── 3. Сборка .dmg ──
info "Создание .dmg…"
DMG_NAME="$DIST_DIR/SP-404SX-Manager.dmg"
rm -f "$DMG_NAME"

# Временная папка для DMG-содержимого
DMG_TMP="$DIST_DIR/dmg_tmp"
rm -rf "$DMG_TMP"; mkdir -p "$DMG_TMP"
cp -R "$APP_PATH" "$DMG_TMP/"
ln -s /Applications "$DMG_TMP/Applications"

hdiutil create -volname "$APP_NAME" \
    -srcfolder "$DMG_TMP" \
    -ov -format UDZO \
    "$DMG_NAME"

rm -rf "$DMG_TMP"

info "════════════════════════════════════════"
info "✅ Сборка завершена!"
info "   App: $APP_PATH"
info "   DMG: $DMG_NAME"
info "════════════════════════════════════════"
echo ""
echo "Установка: открой .dmg и перетащи приложение в Applications."
echo "При первом запуске: правый клик → Открыть (обход Gatekeeper)."
