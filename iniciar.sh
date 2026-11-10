#!/bin/sh
# Abre a BugiCaixa (Linux / macOS). Requer apenas Python 3.8+.
cd "$(dirname "$0")" || exit 1
exec python3 -m bugicaixa "$@"
