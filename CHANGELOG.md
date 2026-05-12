# Changelog

All notable changes to `wdist` are documented here. This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

Installed copies auto-update on Claude Code startup. To force an update now: `/plugin update wdist@wdist`.

## [0.1.0] - 2026-05-06

### Added
- Initial release. `/wdist` produces a short Slack-friendly daily recap of your Claude Code sessions; `--verbose` produces the full structured report.
- Recap is also written to `~/claude-recaps/YYYY-MM-DD.md` for later reuse.
