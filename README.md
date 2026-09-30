# vnu-eoffice

Retrieve documents from the **VNU e-office** (SELAB NetOffice) at
<https://eoffice.vnu.edu.vn/qlvb/> — **fully local**.

It logs into the *local "Office account"* form with your username/password,
polls both document modules — **Văn bản đến** (incoming) and **Văn bản đi**
(outgoing) — and can download attachments. In the OpenClaw deployment, all
external delivery is handled by the authenticated host queue with an explicit
channel and target; this package has no bot-token discovery or direct sender.

> No document text or metadata is sent to any third-party AI service. This
> package connects only to `eoffice.vnu.edu.vn`; an authorized host delivery
> worker is a separate capability.

---

## Features

- 🔐 Local username/password login (PHPSESSID session); no SSO required.
- 📥 Both modules: **Văn bản đến** (`office/receive`) and **Văn bản đi** (`office/dispatch`).
- 🔔 Queue-only OpenClaw delivery with an explicit channel and target policy.
- 📎 Optional attachment download; cleanup remains an explicit caller action.
- ⏰ Cross-platform scheduling: **cron** (Linux/macOS) or **Task Scheduler** (Windows).
- 🧰 Dedup by document id, baseline-on-first-run (no backlog spam).
- 🔢 Numbered latest/search/monitor results, with saved item numbers for
  follow-up `download --item` requests.

## Install

```bash
git clone https://github.com/hoanganhduc/vnu-eoffice.git
cd vnu-eoffice
pip install -e .
```

Requires Python ≥ 3.10. Dependencies: `requests`, `beautifulsoup4`.

## Configure credentials

Secrets are **never** stored in the repo. They are read from environment
variables, from `~/.config/vnu-eoffice/secrets.json`, or from a JSON file
specified with `VNU_SECRETS_FILE`. Required keys:

```json
{
  "VNU_EOFFICE_USERNAME": "your-username",
  "VNU_EOFFICE_PASSWORD": "your-password"
}
```

Equivalent env vars: `VNU_EOFFICE_USERNAME`, `VNU_EOFFICE_PASSWORD`.

## Quick start

```bash
# 1. Verify login and see document counts
vnu-eoffice test-login

# 2. Inspect documents without external delivery
vnu-eoffice list --limit 20
vnu-eoffice monitor --once --dry-run
```

## Commands

| Command | Purpose |
|---|---|
| `test-login` | Verify credentials; print document counts for both modules. |
| `setup-telegram [--chat-id N]` | Retired compatibility command; direct delivery is disabled. |
| `list [--modules den,di] [--limit N]` | List recent documents and save numbered items. |
| `search <keywords> [--modules den,di]` | Search documents and save numbered items. |
| `items [--source latest\|search\|monitor]` | Show the saved item numbers again. |
| `download --id den:<intid>` | Download one document's attachments by direct id. |
| `download --item 2,4` | Download attachments by saved item number. |
| `send --item 2 --delete-after` | Retired compatibility command; use the OpenClaw host queue. |
| `monitor [options]` | One local polling pass: fetch → report → (download) → (delete). |
| `schedule [options]` | Install/preview/remove the recurring scheduled job. |

`list`, `search`, and `monitor` runs number retrieved documents as
`1.`, `2.`, ... and persist the mapping locally. Use `items` to show the saved
numbers again, then `download --item 2` or `download --all`.

### `monitor` options

```
--modules den,di       Which modules to poll (default both)
--limit 60             How many recent docs to scan per module
--download             Download attachments of alerted documents
--delete-after         Delete downloaded files after the polling pass
--send-files           Retired compatibility flag; direct delivery is disabled
--no-notify            Compatibility flag; monitor output is local
--dry-run              No downloads, sends, or state writes
--quiet                Suppress alert subject lines in output
```

### `schedule` options

```
--every 15             Minutes between runs
--modules den,di       Modules to poll
--download             (passed through to monitor)
--delete-after         (passed through to monitor)
--preview              Print the cron / schtasks line without installing
--remove               Remove the installed schedule
```

Scheduled jobs use quiet monitor output by default.

## Privacy & the `--delete-after` option

- Default `monitor` (without `--download`) writes only local state/log data.
- With `--download`, attachments are saved under
  `~/.local/share/vnu_eoffice/documents/<module>/<number>_<id>/`.
- Add `--delete-after` to remove those files (and the now-empty folder) after
  the polling pass.
- Direct Telegram notification and `--send-files` are retired. OpenClaw delivery
  must go through the authenticated host queue with an explicit channel and
  target.
- Scheduled monitor output suppresses report subject lines by default, reducing
  sensitive metadata retained in local cron logs.

## Documentation

- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — secrets, env vars, data
  locations, tuning, scheduling details.
- [`docs/ENDPOINTS.md`](docs/ENDPOINTS.md) — the reverse-engineered SELAB
  NetOffice API this package talks to.

## Notes & limitations

- This uses your own account to read your own documents. Polling is gentle
  (one page per module per run); keep the interval reasonable. Respect your
  institution's acceptable-use rules.
- It scrapes an undocumented ExtJS backend, so a site redesign or a switch to
  SSO-only login could require updates.
- It does not OCR scanned attachments. Reports use document metadata only.
- VNU documents may be marked internal/confidential. Keep downloads on a machine
  you control and prefer `--delete-after`; review the destination before queueing
  any file for external delivery.

## License

MIT — see [LICENSE](LICENSE).
