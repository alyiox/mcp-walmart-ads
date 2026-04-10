# Snapshot Reports API (Sponsored Search)

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/create-report-snapshot-updated
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-snapshot-v2-reports-updated
- https://developer.walmart.com/advertising-partners-search/docs/create-entity-snapshot
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-campaign-entity-snapshots
- https://developer.walmart.com/advertising-partners-search/docs/sample-requests-for-create-report-snapshot-updated
- https://developer.walmart.com/advertising-partners-search/docs/sample-responses-for-create-snapshot-requests-updated
- https://developer.walmart.com/advertising-partners-search/docs/parameters-generated-by-snapshot-reports-v2-updated
- https://developer.walmart.com/advertising-partners-search/docs/report-type-availability-for-snapshot-v2-endpoint-campaign-type-and-advertiser-type-updated
- https://developer.walmart.com/advertising-partners-search/docs/applicable-placements-for-campaign-types-auto-bidded-keyword-bidded-sponsored-brands-and-sponsored-videos-updated
- https://developer.walmart.com/advertising-partners-search/docs/sample-requests-for-create-entity-snapshot
- https://developer.walmart.com/advertising-partners-search/docs/sample-responses-for-create-entity-snapshot

## Performance report snapshot

### Request snapshot

```
POST /api/v2/snapshot/report
```

Body:
- `advertiserId` (integer, required) — advertiser identifier
- `reportType` (string, required) — one of: `adGroup`, `adItem`, `brand`, `category`, `itemHealth`, `itemKeyword`, `keyword`, `outOfBudgetRecommendations`, `pageType`, `platform`, `placement`, `attributedPurchases`, `searchImpression`, `videoCampaigns`, `videoKeywords`
- `reportMetrics` (string, required) — dimensions and metrics for the snapshot; must include at least one dimension (varies by report type)
- `reportDate` (date `yyyy-MM-dd`, conditional) — single snapshot date; last 90 days, cannot be current date
- `startDate` (date `yyyy-MM-dd`, conditional) — first day of date range; cannot be current date
- `endDate` (date `yyyy-MM-dd`, conditional) — last day of date range; cannot be current date

Date rules:
- Use `reportDate` alone **or** `startDate`/`endDate` together — never both.
- No date required for: `outOfBudgetRecommendations`, `searchImpression`, `itemHealth`.

Response: `{ "code": "success", "snapshotId": "..." }`

### Retrieve snapshot

```
GET /api/v2/snapshot
```

Query params:
- `advertiserId` (string, required)
- `snapshotId` (string, required)

Response:
- `code` (string) — `success` or `failure`
- `snapshotId` (string)
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`
- `details` (string) — download URL when `jobStatus` is `done`

Output is CSV compressed with gzip. Files expire after one day.

## Campaign entity snapshot

### Request entity snapshot

```
POST /api/v1/snapshot/entity
```

Query params:
- `advertiserId` (integer, required) — advertiser identifier
- `entityStatus` (string, required) — `enabled`, `disabled`, or `all` (default: `enabled`)
- `entityTypes` (string array, required) — one or more of: `campaign`, `adGroup`, `keyword`, `adItem`, `bidMultiplier`, `placement`, `sbaProfile`, `adGroupMedia`, `category`
- `format` (string, optional) — `gzip` or `zip` (default: `zip`)

Entity type notes:
- `placement` — returns included/excluded placements per campaign
- `sbaProfile` — Sponsored Brands campaigns only
- `adGroupMedia` — Sponsored Video campaigns only
- `category` — Sponsored Brand campaigns only

Response: `{ "snapshotId": "..." }`

### Retrieve entity snapshot

```
GET /api/v1/snapshot
```

Query params:
- `advertiserId` (string, required)
- `snapshotId` (string, required)

Response:
- `code` (string) — `success` or `failure`
- `snapshotId` (string)
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`
- `details` (string) — download URL when `jobStatus` is `done`

Output is JSON in zip/gzip containing arrays: `campaigns`, `adGroups`, `keywords`, `adItem`, `placementBidMultipliers`, `platformBidMultipliers`, `sbaProfiles`, `adGroupMedias`. Files expire after one day.

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
- No limit on number of snapshot requests per advertiser.
- Large responses are truncated in the tool result; full data available via `wmc://responses/{request_id}`.
