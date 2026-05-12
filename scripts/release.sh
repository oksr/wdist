#!/usr/bin/env bash
# Bump plugin version and prepare a release.
#
# Usage: scripts/release.sh <version>     e.g. scripts/release.sh 0.2.0
#
# Bumps version in .claude-plugin/plugin.json and .claude-plugin/marketplace.json,
# prepends a CHANGELOG.md stub, and prints the commit/tag commands.
# Does NOT commit, tag, or push — review the diff first, fill in the CHANGELOG
# body, then run the printed git commands.

set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "Usage: $(basename "$0") <version>  (e.g. 0.2.0)" >&2
  exit 1
fi
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version must be MAJOR.MINOR.PATCH (got: $VERSION)" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree not clean. Commit or stash first." >&2
  exit 1
fi

python3 - "$VERSION" <<'PY'
import pathlib
import re
import sys
from datetime import date

version = sys.argv[1]
today = date.today().isoformat()

# Regex-based version bumping preserves the original JSON formatting
# (em-dashes, inline arrays, etc) — a parse+dump round-trip would
# re-escape unicode and reflow arrays.
version_re = re.compile(r'("version"\s*:\s*)"[^"]+"')
for path in [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"]:
    p = pathlib.Path(path)
    p.write_text(version_re.sub(rf'\1"{version}"', p.read_text()))

changelog = pathlib.Path("CHANGELOG.md")
text = changelog.read_text()
stub = f"## [{version}] - {today}\n\n### Changed\n- TODO: describe what changed\n\n"

marker = "\n## ["
idx = text.find(marker)
if idx == -1:
    changelog.write_text(text.rstrip() + "\n\n" + stub)
else:
    changelog.write_text(text[: idx + 1] + stub + text[idx + 1 :])
PY

cat <<EOF

Bumped to v$VERSION.

Next steps:
  1. Edit CHANGELOG.md to fill in the v$VERSION entry.
  2. git add -A && git commit -m "release: v$VERSION"
  3. git tag v$VERSION && git push && git push --tags
EOF
