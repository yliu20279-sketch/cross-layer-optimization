#!/bin/sh
cd "$(dirname "$0")/sniper"
timeout 600 make -j4 > ../sniper_build.log 2>&1
rc=$?
printf '{"returncode":%s}
' "$rc" > ../SNIPER_BUILD_EXIT.json
exit "$rc"
