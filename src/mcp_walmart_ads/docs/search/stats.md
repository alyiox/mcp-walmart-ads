# Stats API (Sponsored Search)

Near real-time metrics, latest report date, and API usage endpoints.

## Near real-time metrics

Reference: https://developer.walmart.com/advertising-partners-search/docs/retrieve-todays-near-real-time-metrics-and-campaign-cap-out-insights

Retrieve today's running spend and impression metrics plus cap-out insights for active campaigns.

```
GET /api/v2/stats
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional) — filter to a single campaign

Response fields:
- `campaignId`
- `campaignName`
- `spend` — today's spend so far
- `impressions` — today's impressions so far
- `clicks` — today's clicks so far
- `capOutStatus` — `true` if daily budget exhausted
- `remainingBudget` — remaining daily budget

Data lag: approximately 1–3 hours behind real time.

## Latest report date

Reference: https://developer.walmart.com/advertising-partners-search/docs/get-latest-report-date

Returns the most recent date for which snapshot report data is available.

```
GET /api/v1/reportDate
```

Query params:
- `advertiserId` (integer, required)

Response:
- `latestReportDate` (date `yyyy-MM-dd`)

Use this before requesting a snapshot to confirm data is available for a given date.

## API usage analyzer

Reference: https://developer.walmart.com/advertising-partners-search/docs/get-last-hour-api-usage

Returns API call counts for the last hour, broken down by endpoint. Use to monitor rate limit consumption.

```
GET /api/v1/apiUsage
```

Query params:
- `advertiserId` (integer, required)

Response: array of usage objects.

Fields:
- `endpoint` — API path
- `requestCount` — calls made in the last hour
- `rateLimit` — allowed calls per hour
- `remaining` — calls remaining in the current window
