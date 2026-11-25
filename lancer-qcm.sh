#!/bin/sh
# macOS / Linux : interface HTML par défaut, --terminal pour le mode texte.
set -eu
quiz_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
cd "$quiz_dir"
export PYTHONUTF8=1
if [ -n "${QCM_PYTHON:-}" ]; then
    quiz_python=$QCM_PYTHON
elif command -v python3 >/dev/null 2>&1; then
    quiz_python=$(command -v python3)
elif command -v python >/dev/null 2>&1; then
    quiz_python=$(command -v python)
else
    printf '%s\n' 'Python 3.10 ou plus récent est nécessaire pour lancer le QCM.' >&2
    exit 127
fi
if ! "$quiz_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    printf '%s\n' 'Le Python sélectionné ne convient pas : version 3.10 minimum.' >&2
    exit 1
fi
case "${1:-}" in
    --terminal)
        shift
        exec "$quiz_python" "$quiz_dir/app/cli.py" "$@"
        ;;
    --help|-h)
        printf '%s\n' 'Utilisation : sh lancer-qcm.sh [--terminal] [options]' 'Sans option : interface HTML.' '--terminal : QCM dans le terminal (même progression).' 'Python spécifique : QCM_PYTHON=/chemin/python3 sh lancer-qcm.sh'
        ;;
    *)
        exec "$quiz_python" "$quiz_dir/app/serve.py" "$@"
        ;;
esac
