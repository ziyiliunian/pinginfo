#!/bin/bash
set -e
echo "=== PingInfo AppImage Build ==="
cd "$(dirname "$0")"
python3 -c "import PyQt5" 2>/dev/null || python3 -m pip install --user PyQt5
python3 -c "import PyInstaller" 2>/dev/null || python3 -m pip install --user PyInstaller
rm -rf build/dist build/AppDir 2>/dev/null
mkdir -p build
cd build
pyinstaller --noconfirm --name pinginfo --windowed --onedir --add-data ../src:src --hidden-import PyQt5.QtCore --hidden-import PyQt5.QtWidgets --hidden-import PyQt5.QtGui ../src/main.py
echo "PyInstaller done"

# Prepare AppDir
echo "Preparing AppDir..."
mkdir -p AppDir/usr/bin AppDir/usr/share/applications AppDir/usr/share/icons/hicolor/256x256/apps
cp -r dist/pinginfo/* AppDir/usr/bin/ 2>/dev/null
cp ../src/pinginfo.desktop AppDir/usr/share/applications/
cp ../src/pinginfo.desktop AppDir/pinginfo.desktop

# Create AppRun
cat > AppDir/AppRun << 'EOF'
#!/bin/bash
HERE=$(dirname "$(readlink -f "$0")")
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/pinginfo" "$@"
EOF
chmod +x AppDir/AppRun

# Generate icon
python3 -c "
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QRect
pix = QPixmap(256, 256)
pix.fill(QColor('#2196F3'))
p = QPainter(pix)
p.setPen(QColor('white'))
p.setFont(QFont('Arial', 72, QFont.Bold))
p.drawText(QRect(0, 0, 256, 256), Qt.AlignCenter, 'P')
p.end()
pix.save('AppDir/pinginfo.png', 'PNG')
pix.save('AppDir/usr/share/icons/hicolor/256x256/apps/pinginfo.png', 'PNG')
print('Icon generated')
" 2>&1

# Get appimagetool
APPIMAGETOOL="appimagetool"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O "$APPIMAGETOOL" || true
    chmod +x "$APPIMAGETOOL" 2>/dev/null || true
fi

# Build AppImage
OUTPUT="../PingInfo-x86_64.AppImage"
cd ..
if [ -f "build/$APPIMAGETOOL" ]; then
    echo "Building AppImage..."
    ARCH=x86_64 ./build/$APPIMAGETOOL build/AppDir "$OUTPUT" 2>&1 || echo "AppImage build failed"
fi

if [ -f "$OUTPUT" ]; then
    chmod +x "$OUTPUT"
    echo "=== SUCCESS: $OUTPUT ==="
else
    echo "=== AppImage not built, but PyInstaller package is ready ==="
    echo "Run: ./build/dist/pinginfo/pinginfo"
fi
