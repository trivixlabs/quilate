#!/bin/sh
# Instala os hooks que rodam a trava de termos proibidos. Pode rodar mais de uma vez.
set -eu
cd "$(git rev-parse --show-toplevel)"
hooks="$(git rev-parse --git-path hooks)"
mkdir -p "$hooks"
printf '#!/bin/sh\nexec python3 scripts/forbidden_terms.py --staged\n' > "$hooks/pre-commit"
printf '#!/bin/sh\nexec python3 scripts/forbidden_terms.py --message "$1"\n' > "$hooks/commit-msg"
chmod +x "$hooks/pre-commit" "$hooks/commit-msg"
echo "Hooks instalados em $hooks"
