#!/bin/bash

if [ $# -ne 2 ]
then
  head -n 1 $1 | tr ',' "\n" | column
else
    awk -F, -v fields="$2" -f ~/gradu/code/analyzer/examine.awk $1 | column -t -s, | less
fi
