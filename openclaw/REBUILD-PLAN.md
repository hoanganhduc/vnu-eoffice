# VNU eOffice OpenClaw Rebuild Plan

Scope: rebuild the local OpenClaw-facing `vnu-eoffice` adapter from this
repository without turning the ai-agents-skills canonical skill into an
OpenClaw-only copy.

Separation rules:

- The ai-agents-skills repository owns the target-neutral `vnu-eoffice` skill
  instructions and install-target metadata.
- This repository owns the concrete OpenClaw adapter files under
  `openclaw/vnu_eoffice/`.
- OpenClaw runtime state, secrets, downloaded documents, and cron history stay
  outside both repositories.
- Do not commit secret values, secret setup commands, browser state, downloaded
  documents, or generated monitor state.

Recommended rebuild shape:

1. Treat `~/ai-agents-skills/canonical/skills/vnu-eoffice/SKILL.md` as the
   reusable target-neutral instructions.
2. Treat `openclaw/vnu_eoffice/` as generated/adapter material for OpenClaw:
   `SKILL.md`, `run_vnu_eoffice.sh`, and `vnu_eoffice_openclaw.py`.
3. Mirror the Python package into the OpenClaw workspace runtime so
   `/workspace/skills/vnu-eoffice/run_vnu_eoffice.sh` can import `vnu_eoffice`.
4. Keep OpenClaw credentials and Telegram runtime configuration in the local
   OpenClaw secret store only.
5. Keep the OpenClaw cron payload pointed at the workspace-visible launcher, not
   a host-only path.

Verification checklist:

- Canonical ai-agents skill plans for all supported install targets.
- Explicit OpenClaw fake-root planning is not blocked by canonical support
  files.
- The real OpenClaw cron payload uses `/workspace/skills/vnu-eoffice/...`.
- Monitor output includes a title, both incoming and outgoing categories,
  ignores read/unread status, and uses multi-page fetch.
- Latest/search output records numbered items that can be replayed with
  `items`.
- Download requests by item number send files through Telegram and delete local
  copies by default.
- Secret scans over canonical skill files and generated OpenClaw adapter files
  report no credential values.
