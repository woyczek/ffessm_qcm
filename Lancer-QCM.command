#!/bin/sh
quiz_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd) || exit 1
sh "$quiz_dir/lancer-qcm.sh" "$@"
quiz_exit=$?
if [ "$quiz_exit" -ne 0 ] && [ -t 0 ]; then
    printf '\n%s' 'Appuie sur Entrée pour fermer cette fenêtre. '
    read -r quiz_reply
fi
exit "$quiz_exit"
