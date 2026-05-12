# Changelog

All notable changes to `wdist` are documented here. This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

To pull the latest version: `/plugin update wdist@wdist`. Auto-update on Claude Code startup is opt-in — enable it via `/plugin` → Marketplaces → `wdist`.

## [0.2.0] - 2026-05-12

### Added
- Recap output now surfaces GitHub Releases published on the target date. The extractor walks each session's cwd for a `github.com` origin and queries `gh release list`, emitting a top-level `releases` array. Skipped silently if `gh` is unavailable or the cwd has no GitHub remote — the rest of the recap is unaffected.
- Release flow: `CHANGELOG.md`, `scripts/release.sh`, and a "Releasing" section in `CLAUDE.md`. Installed copies auto-update on Claude Code startup whenever `version` bumps.

### Changed
- Short-mode format is tighter: 3–7 bullets (down from 3–10), aim for under ~90 characters per bullet, and strip all identifiers (commit hashes, PR numbers, CI run IDs, URLs, branch/file/ticket paths). Identifiers remain in verbose mode where they belong.
- Synthesis rules in `commands/wdist.md` now split between format-shared and short-only, so the "quote concrete references" rule no longer contradicts short mode.

## [0.1.0] - 2026-05-06

### Added
- Initial release. `/wdist` produces a short Slack-friendly daily recap of your Claude Code sessions; `--verbose` produces the full structured report.
- Recap is also written to `~/claude-recaps/YYYY-MM-DD.md` for later reuse.
