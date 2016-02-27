#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[@]}" )" && pwd )"
echo $DIR

FILENAME=$1

if [ $# -lt 2 ]; then
  echo -e "Available fields to use as second parameter\n(separate several fields with commas)\n"
  head -n 1 $FILENAME | tr ',' "\n" | column
else
    shift
    FIELDNAMES="$@"
    echo $FIELDNAMES
    awk -F, -v fieldnames="$FIELDNAMES" -f "$DIR/examine.awk" $FILENAME  | column -t -s, | less
fi
