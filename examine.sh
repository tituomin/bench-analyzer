#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[@]}" )" && pwd )"

FILENAME=$1

if [ $# -lt 1 ]; then
    echo "Usage: examine.sh filename [fields...]"
elif [ $# -lt 2 ]; then
    cat <<EOF
Available fields to use as further parameters
(separate several fields with spaces)
EOF
    head -n 1 $FILENAME | tr ',' "\n" | column
else
    shift
    FIELDNAMES="$@"
    echo $FIELDNAMES
    awk -F, -v fieldnames="$FIELDNAMES" -f "$DIR/examine.awk" $FILENAME  | column -t -s, | less
fi
