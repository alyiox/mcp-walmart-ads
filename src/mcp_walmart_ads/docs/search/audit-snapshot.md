# Audit Snapshot API (Sponsored Search)

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/create-audit-snapshot
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-audit-snapshots

Provides a history of changes made to campaigns, ad groups, keywords, and items. Use for change tracking and compliance auditing.

## Create audit snapshot

```
POST /api/v1/snapshot/audit
```

Body:
- `advertiserId` (integer, required)
- `startDate` (date `yyyy-MM-dd`, required) — beginning of audit window
- `endDate` (date `yyyy-MM-dd`, required) — end of audit window
- `entityTypes` (string array, optional) — filter to specific entity types: `campaign`, `adGroup`, `keyword`, `adItem`
- `format` (string, optional) — `zip` or `gzip` (default: `zip`)

Response:
- `code` (string) — `success` or `failure`
- `snapshotId` (string)
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`

## Retrieve audit snapshots

```
GET /api/v1/snapshot
```

Query params:
- `advertiserId` (string, required)
- `snapshotId` (string, required)

Poll until `jobStatus` is `done`, then download from `details` URL.

## Output fields

Each row represents one change event:

- `entityType` — `campaign` | `adGroup` | `keyword` | `adItem`
- `entityId` — ID of the changed entity
- `entityName`
- `fieldChanged` — name of the field that was modified
- `oldValue`
- `newValue`
- `changedBy` — user or API client that made the change
- `changeTimestamp` — ISO 8601 datetime

## Notes

- Audit window max: 90 days.
- Files expire 24 hours after generation.
- Sample requests: https://developer.walmart.com/advertising-partners-search/docs/sample-requests-for-create-audit-snapshot
- Sample responses: https://developer.walmart.com/advertising-partners-search/docs/sample-responses-for-create-audit-snapshot
