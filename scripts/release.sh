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
import json
import pathlib
import sys
from datetime import date

version = sys.argv[1]
today = date.today().isoformat()

plugin_path = pathlib.Path(".claude-plugin/plugin.json")
plugin = json.loads(plugin_path.read_text())
plugin["version"] = version
plugin_path.write_text(json.dumps(plugin, indent=2) + "\n")

market_path = pathlib.Path(".claude-plugin/marketplace.json")
market = json.loads(market_path.read_text())
market["metadata"]["version"] = version
market["plugins"][0]["version"] = version
market_path.write_text(json.dumps(market, indent=2) + "\n")

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
