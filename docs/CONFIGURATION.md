# Configuration

`vnu-eoffice` reads secrets and runtime state from your local machine. Do not
put credentials, downloaded documents, state files, or logs in the repository.

## Secrets

Credentials can be supplied either through environment variables or through a
JSON secrets file. Environment variables take precedence.

Default secrets file:

```bash
~/.config/vnu-eoffice/secrets.json
```

Override path explicitly:

```bash
export VNU_SECRETS_FILE=/path/to/secrets.json
```

Expected keys:

```json
{
  "VNU_EOFFICE_USERNAME": "your-office-account",
  "VNU_EOFFICE_PASSWORD": "your-password",
  "TELEGRAM_BOT_TOKEN": "123456:ABC-...",
  "TELEGRAM_CHAT_ID": "optional-chat-id"
}
```

Equivalent environment variables:

```bash
export VNU_EOFFICE_USERNAME='your-office-account'
export VNU_EOFFICE_PASSWORD='your-password'
export TELEGRAM_BOT_TOKEN='123456:ABC-...'
export TELEGRAM_CHAT_ID='optional-chat-id'
```

`VNU_BASE_URL` is intentionally restricted to `https://eoffice.vnu.edu.vn/qlvb/`
for normal use because login posts your Office-account password. For a trusted
test system only, set:

```bash
export VNU_ALLOW_NON_VNU_BASE_URL=1
export VNU_BASE_URL='https://trusted-test-host/qlvb/'
```

## Runtime Paths

Default data directory:

```bash
~/.local/share/vnu_eoffice/
```

Files under this directory include:

| Path | Purpose |
|---|---|
| `state/seen.json` | Dedup state for already-seen document ids. |
| `state/telegram.json` | Locally saved Telegram chat id from `setup-telegram`. |
| `documents/` | Optional downloaded document attachments. |
| `monitor.log` | Cron output when the scheduler is installed. |

Overrides:

```bash
export VNU_DATA_DIR=/path/to/state-root
export VNU_DOCS_DIR=/path/to/downloaded-documents
```

## First Run

Run:

```bash
vnu-eoffice test-login
```

This verifies the local Office-account login and prints document counts for the
incoming and outgoing modules.

Then wire Telegram:

```bash
vnu-eoffice setup-telegram
```

If the bot has not received any message yet, open Telegram and send `/start` to
the bot, then run `setup-telegram` again. If multiple chats are returned, choose
one explicitly:

```bash
vnu-eoffice setup-telegram --chat-id 123456789
```

## Monitoring

Preview what would be scored without sending alerts or writing state:

```bash
vnu-eoffice monitor --once --dry-run --no-notify
```

Run one real polling pass:

```bash
vnu-eoffice monitor --once
```

The first real pass records a baseline and does not alert on the backlog. Later
passes alert only on new documents whose score meets the selected threshold.

Common options:

```bash
vnu-eoffice monitor --once \
  --modules den,di \
  --limit 60 \
  --min-level MEDIUM
```

Use downloads only when needed:

```bash
vnu-eoffice monitor --once --download
```

Delete local attachment copies after alerting:

```bash
vnu-eoffice monitor --once --download --delete-after
```

When `--delete-after` is set, downloaded files are removed even if notification
delivery fails. The next retry can download them again if needed.

Send files to Telegram only if you intentionally want document contents to leave
the machine:

```bash
vnu-eoffice monitor --once --download --send-files
```

Use quiet output for cron-style logs:

```bash
vnu-eoffice monitor --once --quiet
```

## Scheduling

Preview the scheduler command:

```bash
vnu-eoffice schedule --every 15 --preview
```

Install recurring monitoring every 15 minutes:

```bash
vnu-eoffice schedule --every 15
```

Scheduled jobs add `--quiet` automatically, so local logs contain counts and
errors rather than alert subject lines. Intervals must be positive. Values above
59 minutes must be whole hours, such as `60` or `120`; ambiguous intervals such
as `90` are rejected.

Remove the installed schedule:

```bash
vnu-eoffice schedule --remove
```

On Linux and macOS this manages a tagged crontab entry. On Windows it generates
a Task Scheduler entry with `schtasks`.

## Scoring Tuning

Scoring rules live in `vnu_eoffice/importance.py`.

The `RULES` mapping is intentionally simple: each category contributes the best
matching phrase found in the document subject plus sender/recipient text. Add
unit names, personal names, or project terms under `Liên quan trực tiếp` to
boost documents that concern you directly.

Thresholds:

| Level | Score |
|---|---:|
| `HIGH` | `>= 8` |
| `MEDIUM` | `>= 4` |
| `LOW` | `< 4` |

## Privacy Notes

- Metadata alerts go to Telegram when notification is enabled.
- Attachments are not downloaded unless `--download` is passed.
- Attachment contents are not sent to Telegram unless `--send-files` is passed.
- `--delete-after` removes downloaded local copies after the alert attempt.
- No document text is sent to external AI services by this package.

## Troubleshooting

`Missing VNU credentials`
: Set `VNU_EOFFICE_USERNAME` and `VNU_EOFFICE_PASSWORD` in the environment or
  in the configured secrets file.

`No TELEGRAM_BOT_TOKEN`
: Set `TELEGRAM_BOT_TOKEN` in the environment or secrets file.

`No chat_id set`
: Message the bot once in Telegram, then run `vnu-eoffice setup-telegram`.

`Login failed`
: Verify that the account can use the local Office-account login form. The SSO
  button is a different login path and is not implemented by this package.
