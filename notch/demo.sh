#!/bin/sh
# Serve the JSON files in Tests/Fixtures on 127.0.0.1:8000, with the same paths the app reads.
# Lets you see the notch working without the backend and without any secret.
set -e
cd "$(dirname "$0")"

PORT=8000
if nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
    echo "Port $PORT is in use. Stop the Quilate backend first."
    exit 1
fi

pid=
dir=$(mktemp -d)
trap '[ -n "$pid" ] && kill "$pid" 2>/dev/null; rm -rf "$dir"' EXIT
trap 'exit 130' INT TERM
mkdir "$dir/api"
for name in overview verdicts costs; do
    cp "Tests/Fixtures/$name.json" "$dir/api/$name"
done

python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$dir" >/dev/null 2>&1 &
pid=$!
echo "Demo data on http://127.0.0.1:$PORT. Open Quilate.app. Ctrl-C stops."
wait "$pid"
