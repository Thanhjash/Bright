#!/usr/bin/env bash
# Import the Global Success Grade 3 assets the curriculum library refers to.
#
# The library names assets as `asset://gs3/...`; this puts the real files where
# Core resolves them. The files are third-party and gitignored on purpose --
# see .gitignore and docs/research/notes/2026-08-18-changemakers-inputs.md §2.6.
#
#   ./scripts/import-textbook-assets.sh ["/path/to/Changemakers - Inputs"]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-$ROOT/Changemakers - Inputs}"
DST="$ROOT/content/media/gs3"

[ -d "$SRC" ] || { echo "source drop not found: $SRC" >&2; exit 1; }

mkdir -p "$DST/pages" "$DST/audio"

# Printed page N is extracted image (N-1).jpg -- verified against page 10, which
# carries the Track 5 / Track 6 icons the unit map refers to.
for p in 04 06 10 11 12 13 14 15; do
  n=$((10#$p - 1))
  cp -f "$SRC/PDF to images_ GS3_U1_L1/JPG form/$n.jpg" "$DST/pages/p$p.jpg"
done

# Unit 1 uses tracks 5..14.
for t in $(seq 5 14); do
  printf -v pad "%02d" "$t"
  cp -f "$SRC/source_audio/Track $t.mp3" "$DST/audio/track-$pad.mp3"
done

# Panels -- "show a panel, not a page" (gs3-u1-hello/map.md). Whole-page scans
# are unreadable from the back of a room; these are the parts a teacher would
# actually put up. Geometries were derived by visual inspection of the source
# pages (each 1683x2379) and re-verified by opening every output crop -- do
# not regenerate a geometry without checking the result for clipped artwork,
# the tiled publisher watermark, or page furniture (footers, page numbers).
mkdir -p "$DST/panels"
command -v convert >/dev/null 2>&1 || { echo "ImageMagick 'convert' not found" >&2; exit 1; }

# Source resolution is a hard ceiling. The PDF's embedded page images are
# 1151x1622 at 100 ppi; the 1683x2379 JPEG exports we crop from were already
# upsampled from those. Re-extracting at a higher -r gains nothing real, so a
# small panel (the ex.4 option tiles are ~300px) is the material's limit, not
# a mistake in the geometry. Cartoon line art tolerates the upscale on a
# projector; text-heavy panels were checked by eye and are legible.
crop() {
  # crop <source-page.jpg> <geometry WxH+X+Y> <output-panel.jpg>
  convert "$DST/pages/$1" -crop "$2" +repage "$DST/panels/$3"
}

# From p06.jpg -- the character introduction spread.
crop p06.jpg 1450x1980+150+190 char-group.jpg
crop p06.jpg 340x400+195+990   char-ben.jpg
crop p06.jpg 365x400+185+1540  char-mai.jpg
crop p06.jpg 331x400+882+1555  char-minh.jpg
crop p06.jpg 375x420+1185+945  char-lucy.jpg

# From p10.jpg -- Lesson 1 page 1.
crop p10.jpg 810x480+90+540    u1l1-dialogue-a.jpg
crop p10.jpg 770x480+905+540   u1l1-dialogue-b.jpg
crop p10.jpg 980x290+635+1140  u1l1-listen-point-options.jpg
crop p10.jpg 1683x610+0+1470   u1l1-lets-talk-scene.jpg

# From p11.jpg -- Lesson 1 page 2.
crop p11.jpg 670x310+215+245   u1l1-ex4-item1.jpg
crop p11.jpg 300x295+285+255   u1l1-ex4-item1-a.jpg
crop p11.jpg 300x295+575+255   u1l1-ex4-item1-b.jpg
crop p11.jpg 690x310+880+245   u1l1-ex4-item2.jpg
crop p11.jpg 305x295+925+255   u1l1-ex4-item2-a.jpg
crop p11.jpg 300x295+1230+255  u1l1-ex4-item2-b.jpg
crop p11.jpg 470x670+615+1490  u1l1-song-hello-lyrics.jpg

echo "imported $(find "$DST" -type f | wc -l) files into content/media/gs3"
echo "check: python3 -c \"import sys;sys.path.insert(0,'services/classroom-core');from library import unit_catalog;print(len(unit_catalog('gs3-u1-hello')['assets']),'assets referenced')\""
