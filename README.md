# vnu-eoffice

Retrieve, analyse, and alert on documents from the **VNU e-office**
(SELAB NetOffice) at <https://eoffice.vnu.edu.vn/qlvb/> — **fully local**.

It logs into the *local "Office account"* form with your username/password,
polls both document modules — **Văn bản đến** (incoming) and **Văn bản đi**
(outgoing) — scores each new document for importance using a transparent,
keyword-based rule set that runs **entirely on your machine**, and sends a
Telegram alert for the ones that matter. It can optionally download a document's
attachments and delete them again after the alert is sent.

> No document text or metadata is ever sent to any third-party AI service.
> The only outbound traffic is (1) to `eoffice.vnu.edu.vn` to read your own
> documents and (2) to the Telegram Bot API to deliver alerts you asked for.

---

## Features

- 🔐 Local username/password login (PHPSESSID session); no SSO required.
- 📥 Both modules: **Văn bản đến** (`office/receive`) and **Văn bản đi** (`office/dispatch`).
- 🧮 **Local** importance scoring — urgency (`hỏa tốc`, `khẩn`), deadlines
  (`trước ngày`, `hạn nộp`), action cues (`đề nghị`, `góp ý`), meetings
  (`giấy mời`), document type, and important senders. Fully auditable and tunable.
- 🔔 Telegram alerts with subject, sender, deadline, score reasons, and a link.
- 📎 Optional attachment download, with an **opt-in `--delete-after`** to wipe
  local copies once the document has been checked and the alert sent.
- ⏰ Cross-platform scheduling: **cron** (Linux/macOS) or **Task Scheduler** (Windows).
- 🧰 Dedup by document id, baseline-on-first-run (no backlog spam).

## Install

```bash
git clone https://github.com/hoanganhduc/vnu-eoffice.git
cd vnu-eoffice
pip install -e .
# optional Vietnamese OCR for scanned PDFs:  pip install -e ".[ocr]"
```

Requires Python ≥ 3.10. Dependencies: `requests`, `beautifulsoup4`.

## Configure credentials

Secrets are **never** stored in the repo. They are read from
`~/.config/vnu-eoffice/secrets.json` (override with `VNU_SECRETS_FILE`) or from environment
variables. Required keys:

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
| `list [--modules den,di] [--limit N] [--unread]` | List recent documents with scores. |
| `score "<text>"` | Try the scorer on any phrase (offline). |
| `download --module den --id <intid>` | Download one document's attachments. |
| `monitor [options]` | One polling pass: fetch → score → alert → (download) → (delete). |
| `schedule [options]` | Install/preview/remove the recurring scheduled job. |

### `monitor` options

```
--modules den,di       Which modules to poll (default both)
--limit 60             How many recent docs to scan per module
--min-level MEDIUM     Alert threshold: LOW | MEDIUM | HIGH
--download             Download attachments of alerted documents
--delete-after         Delete those downloaded files after the alert is sent
--send-files           Also push the files to Telegram (sends content off-machine)
--no-notify            Don't send Telegram messages (print only)
--dry-run              No downloads, sends, or state writes
```

### `schedule` options

```
--every 15             Minutes between runs
--modules den,di       Modules to poll
--min-level MEDIUM     Alert threshold
--download             (passed through to monitor)
--delete-after         (passed through to monitor)
--preview              Print the cron / schtasks line without installing
--remove               Remove the installed schedule
```

## How importance scoring works

Scoring is plain keyword matching on the lowercased Vietnamese subject (with
diacritics) plus the sender/recipient, summing the best match per category:

| Category | Examples | Weight |
|---|---|---|
| Khẩn (urgency) | hỏa tốc (10), thượng khẩn (9), khẩn (6) | high |
| Hạn chót (deadline) | trước ngày, hạn nộp, chậm nhất | 3–4 |
| Yêu cầu xử lý (action) | đề nghị, yêu cầu, góp ý, báo cáo | 1–3 |
| Họp / Mời (meetings) | giấy mời, cuộc họp, hội nghị | 1–4 |
| Loại văn bản | chỉ thị, quyết định, kế hoạch | 1–3 |
| Nơi gửi quan trọng | Thủ tướng, Chính phủ, Cơ quan ĐHQGHN | 2–5 |

Levels: **HIGH ≥ 8**, **MEDIUM ≥ 4**, otherwise **LOW**. Every point is reported
in the alert ("Lý do"), so you can see *why* a document was flagged.

**Tune it** by editing `RULES` in `vnu_eoffice/importance.py`. The
`Liên quan trực tiếp` category is empty by design — add your unit or name
(e.g. `"khoa học tự nhiên": 3`) to boost documents that concern you directly.

## Privacy & the `--delete-after` option

- Default `monitor` (without `--download`) stores **nothing** on disk; alerts are
  metadata-only.
- With `--download`, attachments are saved under
  `~/.local/share/vnu_eoffice/documents/<module>/<number>_<id>/`.
- Add `--delete-after` to remove those files (and the now-empty folder) right
  after the alert is sent — "check, notify, then forget".
- `--send-files` is the only way document *content* leaves your machine, and it
  is off by default. The metadata alert text still goes to Telegram (your choice
  of channel).

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
- VNU documents may be marked internal/confidential. Keep downloads on a machine
  you control and prefer `--delete-after`; think before using `--send-files`.

## License

MIT — see [LICENSE](LICENSE).
