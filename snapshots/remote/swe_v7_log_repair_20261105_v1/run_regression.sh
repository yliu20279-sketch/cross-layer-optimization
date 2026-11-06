#!/bin/sh
set -eu
cd "$(dirname "$0")"
g++ -std=c++11 -pthread probe.cpp -o probe
event_path="$PWD/regression.events"
test ! -e "$event_path"
MAINT_EVENT_LOG="$event_path" timeout 15 ./probe
python3 strict_parser.py "$event_path"
