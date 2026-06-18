# Fix Plan: Multi-Agent Review Issues

## Goal

Fix the highest-priority failure points found by the multi-agent package review:
alert delivery correctness, Telegram response validation, local cleanup/privacy,
strict endpoint parsing, per-module baseline state, scheduler argument handling,
and focused offline regression coverage.

## Scope

In scope:

- Telegram API response validation.
- Monitor seen-state retry behavior and per-module baseline initialization.
- `--download --delete-after` cleanup on failures.
- Client response validation for list/detail/attachment endpoints.
- Safe local directory/file modes and path-component sanitization.
- CLI/scheduler validation for empty modules and invalid intervals.
- Windows schedule removal support.
- Offline tests for the changed behavior.
- Documentation updates for behavior and privacy notes.

Out of scope:

- Live VNU polling during verification.
- Real Telegram sends.
- Real attachment downloads.
- Installing or removing cron/Task Scheduler entries.
- Implementing OCR.

## Assumptions

- `--no-notify` intentionally consumes matching documents without sending alerts.
- If notification is enabled but Telegram is unavailable, alertable documents should remain retryable.
- First-run baseline should be tracked per module and only recorded for modules fetched successfully.
- The package should prefer clear failures over silently treating HTML/login pages as empty lists.

## Interfaces

- `vnu_eoffice/client.py`
- `vnu_eoffice/monitor.py`
- `vnu_eoffice/notify.py`
- `vnu_eoffice/config.py`
- `vnu_eoffice/scheduler.py`
- `vnu_eoffice/cli.py`
- `tests/`
- `docs/CONFIGURATION.md`

## Acceptance Criteria

- Telegram HTTP errors and `ok: false` responses raise.
- Failed alert delivery does not mark the document seen.
- Downloaded files are deleted when `delete_after=True`, even if sending fails.
- HTML/login responses and malformed endpoint envelopes raise clear client errors.
- Attachment envelopes of the form `{total, results}` are normalized.
- Module initialization is per module and empty module selections are rejected.
- Invalid scheduler intervals are rejected; Windows schedule removal is implemented.
- Runtime directories and sensitive state files are created with private permissions where practical.
- Offline tests cover these behaviors and pass.

## Verification

- `python3 -m unittest discover -v`
- `python3 -m compileall vnu_eoffice tests`
- CLI smoke checks for scheduler preview and invalid scheduler/module args.

## Risks

- Live SELAB NetOffice endpoint behavior remains undocumented and can still change.
- Exact cron semantics beyond common minute/hour intervals remain limited.
- Telegram remains an external trust boundary for metadata alerts.
