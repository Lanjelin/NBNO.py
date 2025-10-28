#!/usr/bin/env bash
set -euo pipefail

# Effective (mounted) tessdata lives here
EFFECTIVE_PARENT="/opt"
EFFECTIVE_TESSDATA="${EFFECTIVE_PARENT}/tessdata"

# System-installed tessdata (Debian/Ubuntu Tesseract 5 path),
# with a fallback to the older path if needed.
SYS_TESSDATA_5="/usr/share/tesseract-ocr/5/tessdata"
SYS_TESSDATA_FALLBACK="/usr/share/tesseract-ocr/tessdata"

if [ -d "$SYS_TESSDATA_5" ]; then
  DEFAULT_SYS_TESSDATA="$SYS_TESSDATA_5"
elif [ -d "$SYS_TESSDATA_FALLBACK" ]; then
  DEFAULT_SYS_TESSDATA="$SYS_TESSDATA_FALLBACK"
else
  echo "Warning: Could not find system tessdata directory. Proceeding without seeding." >&2
  DEFAULT_SYS_TESSDATA=""
fi

# Ensure effective dir exists
mkdir -p "$EFFECTIVE_TESSDATA"

# Seed defaults once (copy only files that don't exist in the volume)
if [ -n "${DEFAULT_SYS_TESSDATA}" ] && [ -d "${DEFAULT_SYS_TESSDATA}" ]; then
  rsync -a --ignore-existing "${DEFAULT_SYS_TESSDATA}/" "${EFFECTIVE_TESSDATA}/"
fi

# Point Tesseract at the effective dir only
# (TESSDATA_PREFIX expects the *parent* of the tessdata folder)
export TESSDATA_PREFIX="$EFFECTIVE_TESSDATA" #"${EFFECTIVE_PARENT}"

# Helpful logs (once)
if [ -n "${DEFAULT_SYS_TESSDATA}" ] && [ -d "${DEFAULT_SYS_TESSDATA}" ]; then
  echo "Seeded tessdata from: ${DEFAULT_SYS_TESSDATA}"
fi
# echo "Effective tessdata: ${EFFECTIVE_TESSDATA}"
# echo "Available languages now:"
if command -v tesseract >/dev/null 2>&1; then
  # Use direct flag to be explicit and avoid surprises
  tesseract --tessdata-dir "${EFFECTIVE_TESSDATA}" --list-langs || true
fi

# Hand off to the real command
exec "$@"
