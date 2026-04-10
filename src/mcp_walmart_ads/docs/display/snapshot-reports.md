# Snapshot Reports API (Display)

Reference:
- https://developer.walmart.com/advertising-partners/docs/create-report-snapshot
- https://developer.walmart.com/advertising-partners/docs/retrieve-snapshots-1
- https://developer.walmart.com/advertising-partners/docs/create-entity-snapshot-1
- https://developer.walmart.com/advertising-partners/docs/sample-requests-and-responses-for-create-report-snapshot
- https://developer.walmart.com/advertising-partners/docs/sample-response-report-snapshot
- https://developer.walmart.com/advertising-partners/docs/sample-requests-and-responses-for-create-entity-snapshot
- https://developer.walmart.com/advertising-partners/docs/sample-response-entity-snapshot
- https://developer.walmart.com/advertising-partners/docs/definition-of-various-parameters-generated-across-the-snapshot-reports
- https://developer.walmart.com/advertising-partners/docs/metric-type-availability-by-report-type

## Performance report snapshot

### Request snapshot

```
POST /api/v1/snapshot/report
```

Body:
- `advertiserId` (integer, required) — advertiser identifier
- `startDate` (date `yyyy-MM-dd`, required) — first day of report data; cannot be current date; data starts at midnight ET
- `endDate` (date `yyyy-MM-dd`, required) — last day of report data; cannot be current date; data includes full day through 23:59:59 ET
- `reportType` (string, required) — one of: `campaign`, `lineItem`, `tactic`, `sku`, `bid`, `newBuyer`, `creative`
- `reportMetrics` (string, optional) — specific metrics to include; omit to return all metrics for the report type
- `scope` (string, optional) — aggregation level: `CAMPAIGN` (default) or `CAMPAIGN_GROUP`
- `attributionWindow` (string, optional) — SKU reports only: `days14` or `days30`
- `salesChannel` (string, optional) — SKU reports only: `stores`, `online`, or `acc`
- `itemsetType` (string, optional) — SKU reports only: `halo`, `featured`, or `total`

Report type availability:

| reportType | Onsite | Offsite |
|------------|--------|---------|
| campaign   | yes    | yes     |
| lineItem   | yes    | yes     |
| tactic     | yes    | yes     |
| sku        | yes    | yes     |
| bid        | yes    | no      |
| newBuyer   | yes    | yes     |
| creative   | yes    | no      |

Response:
- `code` (string) — `success` or `failure`
- `details` (string) — error details on failure
- `snapshotId` (string)
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`

### Retrieve snapshot

```
GET /api/v1/snapshot
```

Query params:
- `advertiserId` (integer, required)
- `snapshotId` (string, required)

Response:
- `code` (string) — `success` or `failure`
- `details` (string) — download URL when `jobStatus` is `done`
- `snapshotId` (string)
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`

Output is gzip-compressed. Contents are CSV (report snapshots) or JSON (entity snapshots). Files expire after one day.

## Entity snapshot

### Request entity snapshot

```
POST /api/v1/snapshot/entity
```

Body:
- `advertiserId` (integer, required) — advertiser identifier
- `entityStatus` (string, required) — `active`, `inactive`, or `all`
- `entityTypes` (string array, required) — one or more of: `campaign`, `lineItem`

Status mapping:
- `active` — returns LIVE/SCHEDULED (Onsite) or ACTIVE (Offsite)
- `inactive` — returns DRAFT/PAUSED (Onsite) or INACTIVE (Offsite)
- `all` — returns all statuses including COMPLETED

Response:
- `code` (string) — `success` or `failure`
- `details` (string) — error details on failure
- `snapshotId` (string)
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`

Retrieve entity snapshots using the same `GET /api/v1/snapshot` endpoint above.

## Notes

- Reporting data may be delayed 24–48 hours from the time of the request.
- SKU reports can generate large files; recommend 15-day maximum date ranges.
- When `scope = CAMPAIGN_GROUP`, only campaigns within groups are included; standalone campaigns are excluded.
- If report data is unavailable for the requested end date, the API fails and returns the latest available date.
- No limit on number of snapshot requests per advertiser (rate limits still apply).
- Separate advertiser IDs exist for Onsite and Offsite display.
- Large responses are truncated in the tool result; full data available via `wmc://responses/{request_id}`.
