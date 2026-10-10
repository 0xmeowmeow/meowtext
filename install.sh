#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else "Meowtext needs Python 3.12 or newer.")'
for program in kitty figlet; do
    if ! command -v "$program" >/dev/null 2>&1; then
        printf 'Missing %s. On Debian/Ubuntu: sudo apt install kitty figlet toilet python3-venv fonts-dejavu-core\n' "$program" >&2
        exit 1
    fi
done
python3 -m venv "$project_dir/.venv"
"$project_dir/.venv/bin/python" -m pip install "$project_dir"
"$project_dir/.venv/bin/python" - "$project_dir" <<'PY'
import os, pathlib, shlex, sys
project = pathlib.Path(sys.argv[1])
launcher = pathlib.Path.home() / '.local/bin/meowtext'
launcher.parent.mkdir(parents=True, exist_ok=True)
content = '#!/bin/sh\n# Meowtext launcher\nexec ' + shlex.quote(str(project / '.venv/bin/meowtext')) + ' "$@"\n'
if launcher.exists() and '# Meowtext launcher' not in launcher.read_text():
    raise SystemExit(f'{launcher} already exists. Your installed editor is {project}/.venv/bin/meowtext; the existing launcher was left alone.')
launcher.write_text(content)
launcher.chmod(0o755)
print(f'Ready. Open Kitty and run: {launcher}')
PY
