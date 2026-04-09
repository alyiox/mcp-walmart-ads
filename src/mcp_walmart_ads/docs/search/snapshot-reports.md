# Snapshot Reports API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/reference/

## Performance report snapshot

### Request snapshot

```
POST /api/v2/snapshot/report
```

Body:
- `advertiserId` (integer, required)
- `startDate` (date `yyyy-MM-dd`, required)
- `endDate` (date `yyyy-MM-dd`, required)
- `reportType` (string, required) — e.g. `itemHealthV2` | `itemKeyword` | `campaign`
- `attributionWindow` (string, optional) — e.g. `days14`
- `format` (string, optional) — e.g. `gzip`

Response: `{ "snapshotId": "..." }`

### Retrieve snapshot

```
GET /api/v2/snapshot/report
```

Query params:
- `advertiserId` (integer, required)
- `snapshotId` (string, required)

Response: report data (may be large — use the resource URI for full content).

## Campaign entity snapshot

### Request entity snapshot

```
POST /api/v1/snapshot/entity
```

Body:
- `advertiserId` (integer, required)

Response: `{ "snapshotId": "..." }`

### Retrieve entity snapshot

```
GET /api/v1/snapshot/entity
```

Query params:
- `advertiserId` (integer, required)
- `snapshotId` (string, required)

## Insight snapshot

### Request insight snapshot

```
POST /api/v1/snapshot/insight
```

Body:
- `advertiserId` (integer, required)
- (additional fields per insight type)

## Notes

- Snapshot IDs expire 24 hours after generation.
- Large responses are truncated in the tool result; full data available via `wmc://responses/{request_id}`.
