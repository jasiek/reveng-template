# firmware/

Put the image here. `.gitignore` excludes the contents by default: vendor firmware
is generally not yours to redistribute, and dumps of your own radio may contain
serial numbers or calibration data specific to your unit.

If you decide a particular file is safe to track, `git add -f` it deliberately.

Record in `TARGET.md`, for every file here: where it came from, its SHA-256, and
what `tools/triage.py` said about it. Six months later "which of these two .bin
files did we actually import?" is a real and annoying question.
