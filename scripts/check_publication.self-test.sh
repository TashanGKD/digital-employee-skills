#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s "$repo/tests" -p test_publication.py -v
