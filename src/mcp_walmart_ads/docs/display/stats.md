# Stats API (Display)

Near real-time delivery metrics and latest report date endpoints.

## Near real-time delivery performance

Reference: https://developer.walmart.com/advertising-partners/docs/real-time-delivery-performance-api

Retrieve today's running or total delivery metrics for campaigns and ad groups.

```
GET /api/v1/stats
```

Query params:
- `advertiserId` (integer, required)
- `campaignIds` (array of integers, conditional) — up to 50; at least one of `campaignIds` or `adGroupIds` required
- `adGroupIds` (array of integers, conditional) — up to 50
- `timeWindow` (string, optional) — `today` | `total` | `all` (default: `total`)

Response:
- `asOf` (string) — ISO 8601 timestamp normalized to ET
- `lastUpdatedAt` (integer) — last refresh timestamp
- `advertiserId` (integer)
- `campaigns` (array):
  - `campaignId` (integer)
  - `metrics` (object with `today` and/or `total` sub-objects)
- `adGroups` (array):
  - `adGroupId` (integer)
  - `campaignId` (integer)
  - `metrics` (object with `today` and/or `total` sub-objects)

Metrics sub-object fields:
- `impressions` (integer)
- `clicks` (integer)
- `adSpend` (float)

## Latest report date

Reference: https://developer.walmart.com/advertising-partners/docs/get-latest-report-date-2

Returns the most recent date for which performance report data has been processed.

```
GET /api/v1/latestReportDate
```

Query params:
- `advertiserId` (integer, required)

Response:
- `advertiserId` (string)
- `latestReportDate` (string `yyyy-MM-dd`) — latest date available for snapshot reports

Use this before requesting a snapshot to confirm data availability for a given date.
