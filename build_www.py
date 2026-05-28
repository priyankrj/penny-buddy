"""Build www/ folder for Capacitor native builds."""
import os
import shutil

SRC = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(SRC, 'www')

FILES = ['index.html', 'app.js', 'styles.css', 'manifest.json', 'sw.js', 'case-study.html']
ICON_EXTS = {'.png', '.jpg', '.svg', '.ico', '.webp'}

# Clean and recreate www/
if os.path.exists(DEST):
    shutil.rmtree(DEST)
os.makedirs(DEST)

# Copy files
for f in FILES:
    src = os.path.join(SRC, f)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(DEST, f))
        print(f'  Copied {f}')

# Copy icons
icons_src = os.path.join(SRC, 'icons')
icons_dest = os.path.join(DEST, 'icons')
if os.path.exists(icons_src):
    os.makedirs(icons_dest, exist_ok=True)
    for f in os.listdir(icons_src):
        if os.path.splitext(f)[1].lower() in ICON_EXTS:
            shutil.copy2(os.path.join(icons_src, f), os.path.join(icons_dest, f))
            print(f'  Copied icons/{f}')

print('\n  www/ folder ready for Capacitor sync.')
