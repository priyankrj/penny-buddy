/**
 * Penny Buddy — Build script
 * Copies web assets into www/ folder for Capacitor native builds
 */
const fs = require('fs');
const path = require('path');

const SRC = __dirname;
const DEST = path.join(__dirname, 'www');

// Files and folders to copy into www/
const FILES = [
  'index.html',
  'app.js',
  'styles.css',
  'manifest.json',
  'sw.js',
  'case-study.html'
];
const DIRS = ['icons'];

// Clean and recreate www/
if (fs.existsSync(DEST)) {
  fs.rmSync(DEST, { recursive: true });
}
fs.mkdirSync(DEST, { recursive: true });

// Copy files
for (const file of FILES) {
  const src = path.join(SRC, file);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, path.join(DEST, file));
    console.log(`  Copied ${file}`);
  }
}

// Copy directories
for (const dir of DIRS) {
  const srcDir = path.join(SRC, dir);
  const destDir = path.join(DEST, dir);
  if (fs.existsSync(srcDir)) {
    fs.mkdirSync(destDir, { recursive: true });
    const files = fs.readdirSync(srcDir);
    for (const f of files) {
      const ext = path.extname(f).toLowerCase();
      // Only copy assets, skip scripts
      if (['.png', '.jpg', '.svg', '.ico', '.webp'].includes(ext)) {
        fs.copyFileSync(path.join(srcDir, f), path.join(destDir, f));
        console.log(`  Copied ${dir}/${f}`);
      }
    }
  }
}

console.log('\n  www/ folder ready for Capacitor sync.');
