#!/usr/bin/env bash
# Have the Pi greet me by name.
#
#   ./greet.sh          Piper, the one we chose
#   ./greet.sh all      the same greeting in every engine, for comparison
#   ./greet.sh espeak   one named engine: espeak, festival, flite, piper
#
# The demo scripts each say a different sentence, so they cannot be compared.
# This says one sentence in all of them.

set -euo pipefail

NAME="Monica"
GREETING="Good evening, $NAME. How was your day?"

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$LAB_DIR/.venv/bin/python"

say_espeak() {
    espeak-ng -ven+f2 -k5 -s150 --stdout "$GREETING" | aplay -q
}

say_festival() {
    echo "$GREETING" | festival --tts
}

say_flite() {
    flite -t "$GREETING"
}

say_piper() {
    "$PYTHON" -m piper \
        --model en_US-lessac-medium \
        --data-dir "$LAB_DIR/voices" \
        --output-raw -- "$GREETING" 2>/dev/null \
        | aplay -q -r 22050 -f S16_LE -t raw -
}

case "${1:-piper}" in
    espeak)   say_espeak ;;
    festival) say_festival ;;
    flite)    say_flite ;;
    piper)    say_piper ;;
    all)
        for engine in espeak festival flite piper; do
            echo "--- $engine ---"
            "say_$engine"
            sleep 1
        done
        ;;
    *)
        echo "unknown engine: $1 (use espeak, festival, flite, piper or all)" >&2
        exit 1
        ;;
esac
