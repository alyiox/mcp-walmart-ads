# Snapshot Reports API (Display)

Reference: https://developer.walmart.com/advertising-partners/reference/

## Request snapshot report

```
POST /api/v1/snapshot/report
```

Body:
- `advertiserId` (integer, required)
- `startDate` (date `yyyy-MM-dd`, required)
- `endDate` (date `yyyy-MM-dd`, required)
- `reportType` (string, required) — e.g. `lineItem`
- `reportMetrics` (array of strings, optional) — e.g. `["campaignGroupId", "date", "impressions", "clicks", "spend"]`
- `scope` (string, optional) — e.g. `CAMPAIGN_GROUP` | `LINE_ITEM`

Response: `{ "snapshotId": "..." }`

## Retrieve snapshot report

```
GET /api/v1/snapshot/report
```

Query params:
- `advertiserId` (integer, required)
- `snapshotId` (string, required)

Response: report data (may be large — use the resource URI for full content).

## Example request

```json
{
  "advertiserId": 239432,
  "startDate": "2026-04-01",
  "endDate": "2026-04-10",
  "reportType": "lineItem",
  "reportMetrics": ["campaignGroupId", "date", "impressions", "clicks", "spend", "sales"],
  "scope": "CAMPAIGN_GROUP"
}
```

## Notes

- Large responses are truncated in the tool result; full data available via `wmc://responses/{request_id}`.
