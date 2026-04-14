#!/usr/bin/env bash
# Clone all 7 sibling service repos next to this meta-repo so `make up` can
# build their images from the filesystem. Safe to re-run.
set -euo pipefail

OWNER=${OWNER:-SamieZian}
PARENT=$(cd "$(dirname "$0")/.." && pwd)

REPOS=(
  eligibility-atlas
  eligibility-member
  eligibility-group
  eligibility-plan
  eligibility-bff
  eligibility-workers
  eligibility-frontend
)

echo "→ cloning sibling repos into $PARENT"
for r in "${REPOS[@]}"; do
  dir="$PARENT/$r"
  if [[ -d "$dir/.git" ]]; then
    echo "  $r: already cloned, pulling"
    (cd "$dir" && git pull --ff-only)
  else
    echo "  $r: cloning"
    git clone "https://github.com/$OWNER/$r.git" "$dir"
  fi
done

echo ""
echo "✅ All repos present. Layout:"
ls -d "$PARENT"/eligibility-* | sed 's|.*/|  |'

echo ""
echo "Next: docker compose up -d  (or: make up)"
