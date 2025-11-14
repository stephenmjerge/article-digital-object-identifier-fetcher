# Codex Guidance

- Run `scripts/run-tests.sh` before shipping changes; it exercises the CLI plus the ingestion pipeline.
- Keep resolver prompts in `docs/prompts` synchronized with any logic updates.
- Never commit PDF assets that include PHI; rely on the redacted samples in `demo-assets/`.
- Document noteworthy behavior updates inside `CHANGELOG.md` and cross-link to the matching roadmap milestone.
