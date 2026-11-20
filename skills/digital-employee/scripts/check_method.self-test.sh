#!/bin/sh
set -eu
METHOD_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 -B -m unittest discover -s "$METHOD_SCRIPT_DIR" -p test_check_method.py
