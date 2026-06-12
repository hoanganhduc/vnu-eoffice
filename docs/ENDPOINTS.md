# SELAB NetOffice Endpoints

This project talks to the authenticated SELAB NetOffice web application behind
`https://eoffice.vnu.edu.vn/qlvb/`. The endpoints below were reverse-engineered
from the ExtJS application and verified with the local Office-account login.

The package uses only the current user's authenticated session and does not use
an official public API.

## Authentication

Base URL:

```text
https://eoffice.vnu.edu.vn/qlvb/
```

Login flow:

1. `GET /qlvb/login/`
2. Extract the hidden `_token` input.
3. `POST /qlvb/login/login.php`
4. Keep the resulting `PHPSESSID` cookie in the same HTTP session.

Posted fields:

| Field | Value |
|---|---|
| `MachineID` | Empty string. |
| `_token` | Token from the login page. |
| `signInControl$UserName` | Office-account username. |
| `signInControl$password` | Office-account password. |

The VNU SSO button is a separate identity-provider flow and is not implemented.

## Modules

Each document module is a separate ExtJS app under the authenticated session.

| Code | Label | Path | Number field | Date field | Party field |
|---|---|---|---|---|---|
| `den` | `Văn bản đến` | `office/receive` | `intSoden` | `strNgayden` | `strCoquanphathanh` |
| `di` | `Văn bản đi` | `office/dispatch` | `intSophathanh` | `strNgayky` | `strNoinhan` |

Outgoing records can have an empty `strNoinhan`; the package falls back to
`strNguoiky` and labels it as the signer.

## List Documents

Endpoint:

```text
GET /qlvb/{module-path}/server/listvb.php
```

Example module paths:

```text
office/receive/server/listvb.php
office/dispatch/server/listvb.php
```

Parameters used by the package:

| Parameter | Meaning |
|---|---|
| `page` | 1-based page number. |
| `start` | Offset, usually `(page - 1) * limit`. |
| `limit` | Number of rows to return. |
| `trichyeu` | Subject search text. |
| `kieuvb` | Document type filter, `-1` for all. |
| `loaivanban` | Document category filter, `0` for all. |
| `sovanban` | Number filter, `0` for all. |
| `trangthaivb` | Read-state filter; `-2` for unread-only, `-1` for all. |
| `trangthai` | Status filter, `-1` for all. |
| `intid` | Specific document id, `0` for all. |
| `favorite` | Favorite filter, `0` for all. |
| `attach` | `1` for has-attachment filter, `0` for all. |
| `butphe` | Comment/instruction filter, `0` for all. |
| `vbtheongay` | Date filter string, empty for all. |
| `xemtatca` | View-all flag, `0` by default. |

Response shape:

```json
{
  "total": 123,
  "results": [
    {
      "intid": "1085800",
      "strKyhieu": "...",
      "strTrichyeu": "...",
      "statusopen": "0",
      "attach": "1"
    }
  ]
}
```

NetOffice may return a UTF-8 BOM and unquoted top-level keys such as:

```text
{ total : 5 , results : [ ... ] }
```

`vnu_eoffice.client._loads_lenient()` handles this by parsing the `total` value
and the `results` array separately when strict JSON parsing fails.

## Document Fields

Common fields:

| Field | Meaning |
|---|---|
| `intid` | Document id used for detail and attachment listing. |
| `strKyhieu` | Document symbol/reference. |
| `strTrichyeu` | Subject/summary. |
| `statusopen` | `"0"` means unread in observed records. |
| `attach` | Non-zero/non-empty means the document has attachments. |
| `strNguoiky` | Signer, especially useful for outgoing records. |

Incoming-specific fields:

| Field | Meaning |
|---|---|
| `intSoden` | Incoming number. |
| `strNgayden` | Incoming date. |
| `strCoquanphathanh` | Issuing agency/sender. |

Outgoing-specific fields:

| Field | Meaning |
|---|---|
| `intSophathanh` | Outgoing issue number. |
| `strNgayky` | Signing date. |
| `strNoinhan` | Recipient. |

## Detail Text

Endpoint:

```text
POST /qlvb/{module-path}/server/viewvb.php
```

Form data:

| Field | Value |
|---|---|
| `id` | Document `intid`. |

The package extracts visible text from the returned HTML with BeautifulSoup.

## Attachments

List attachments:

```text
POST /qlvb/{module-path}/server/attach.list.php
```

Form data:

| Field | Value |
|---|---|
| `id` | Document `intid`. |

Observed attachment records include:

| Field | Meaning |
|---|---|
| `name` | Display filename. |
| `size` | Display size. |
| `date` | Attachment date. |
| `itemId` | File id used by `download.php`. |

Download one attachment:

```text
GET /qlvb/{module-path}/server/download.php?intid={itemId}
```

There is also a multi-file download endpoint used by the web UI, but the package
downloads attachments one at a time so filenames and cleanup are explicit.

## Operational Notes

- Poll gently. The app is an older PHP/ExtJS system, and one page per module per
  polling pass is enough for normal monitoring.
- Dedup by module plus `intid`; incoming and outgoing modules are distinct.
- Treat downloaded files as confidential unless you know otherwise.
- These endpoints can change if SELAB NetOffice is upgraded or VNU changes the
  deployment.
