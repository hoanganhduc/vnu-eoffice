# vnu-eoffice

Retrieve and alert on documents from the **VNU e-office**
(SELAB NetOffice) at <https://eoffice.vnu.edu.vn/qlvb/> — **fully local**.

It logs into the *local "Office account"* form with your username/password,
polls both document modules — **Văn bản đến** (incoming) and **Văn bản đi**
(outgoing) — and sends a Telegram alert for every new document after the first
baseline run. It can optionally download a document's attachments and delete
them again after the alert attempt.

> No document text or metadata is ever sent to any third-party AI service.
> The only outbound traffic is (1) to `eoffice.vnu.edu.vn` to read your own
> documents and (2) to the Telegram Bot API to deliver alerts you asked for.

---

## Features

- 🔐 Local username/password login (PHPSESSID session); no SSO required.
- 📥 Both modules: **Văn bản đến** (`office/receive`) and **Văn bản đi** (`office/dispatch`).
- 🔔 Telegram alerts for every new document, with subject, sender/recipient,
  document metadata, attachment count, and a link.
- 📎 Optional attachment download, with an **opt-in `--delete-after`** to wipe
  local copies once the document has been checked and the alert attempt finishes.
- ⏰ Cross-platform scheduling: **cron** (Linux/macOS) or **Task Scheduler** (Windows).
- 🧰 Dedup by document id, baseline-on-first-run (no backlog spam).
- 🔢 Numbered latest/search/monitor results, with saved item numbers for
  follow-up `download --item` and `send --item` requests.

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
  "VNU_EOFFICE_PASSWORD": "your-password",
  "TELEGRAM_BOT_TOKEN":   "123456:ABC-...",
  "TELEGRAM_CHAT_ID":     "optional — auto-discovered by setup-telegram"
}
```

Equivalent env vars: `VNU_EOFFICE_USERNAME`, `VNU_EOFFICE_PASSWORD`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Quick start

```bash
# 1. Verify login and see document counts
vnu-eoffice test-login

# 2. One-time Telegram wiring: message your bot once (send "/start" in Telegram),
#    then capture the chat id:
vnu-eoffice setup-telegram

# 3. See what would be flagged (no alerts sent)
vnu-eoffice list --limit 20
vnu-eoffice monitor --once --dry-run

# 4. Run a real pass (alerts important new docs via Telegram)
vnu-eoffice monitor --once

# 5. Schedule it every 15 minutes
vnu-eoffice schedule --every 15
```

## Commands

| Command | Purpose |
|---|---|
| `test-login` | Verify credentials; print document counts for both modules. |
| `setup-telegram [--chat-id N]` | Discover & save the Telegram chat id (message the bot first). |
| `list [--modules den,di] [--limit N]` | List recent documents and save numbered items. |
| `search <keywords> [--modules den,di]` | Search documents and save numbered items. |
| `items [--source latest\|search\|monitor]` | Show the saved item numbers again. |
| `download --id den:<intid>` | Download one document's attachments by direct id. |
| `download --item 2,4` | Download attachments by saved item number. |
| `send --item 2 --delete-after` | Send a saved item through Telegram. |
| `monitor [options]` | One polling pass: fetch → alert → (download) → (delete). |
| `schedule [options]` | Install/preview/remove the recurring scheduled job. |

`list`, `search`, and alerting `monitor` runs number retrieved documents as
`1.`, `2.`, ... and persist the mapping locally. Use `items` to show the saved
numbers again, then `download --item 2`, `send --item 2`, or `download --all`.

### `monitor` options

```
--modules den,di       Which modules to poll (default both)
--limit 60             How many recent docs to scan per module
--download             Download attachments of alerted documents
--delete-after         Delete downloaded files after the alert attempt
--send-files           Also push the files to Telegram (sends content off-machine)
--no-notify            Don't send Telegram messages (print only)
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

- Default `monitor` (without `--download`) writes only local state/log data; alerts
  are metadata-only.
- With `--download`, attachments are saved under
  `~/.local/share/vnu_eoffice/documents/<module>/<number>_<id>/`.
- Add `--delete-after` to remove those files (and the now-empty folder) after
  the alert attempt — "check, notify, then forget".
- `--send-files` is the only way document *content* leaves your machine, and it
  is off by default. The metadata alert text still goes to Telegram (your choice
  of channel).
- Scheduled monitor output suppresses alert subject lines by default, reducing
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
- It does not OCR scanned attachments. Alerts use document metadata only.
- VNU documents may be marked internal/confidential. Keep downloads on a machine
  you control and prefer `--delete-after`; think before using `--send-files`.

## License

MIT — see [LICENSE](LICENSE).
