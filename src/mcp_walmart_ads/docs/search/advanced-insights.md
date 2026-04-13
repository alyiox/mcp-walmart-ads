# Advanced Insights API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/docs/overview-18

Provides deep competitive and category-level insights to inform bidding and targeting strategy.

## Request advanced insights snapshot

```
POST /api/v1/snapshot/insight
```

Body:
- `insightType` (string, required) — `advancedInsights`
- `format` (string, required) — `zip` or `gzip`
- `advertiserId` (integer, required)

Response:
- `code` (string) — `success` or `failure`
- `snapshotId` (string)
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`

## Retrieve advanced insights report

```
GET /api/v1/snapshot
```

Query params:
- `advertiserId` (string, required)
- `snapshotId` (string, required)

Poll until `jobStatus` is `done`, then download from `details` URL.

## Report columns

- `reportDate`
- `itemId`
- `itemName`
- `brandName`
- `department`
- `category`
- `subCategory`
- `impressionShare` — estimated share of impressions in the category
- `suggestedBid` — recommended bid for competitive placement
- `competitivenessScore` — index of competition intensity

## Notes

- Report is updated daily.
- Use `suggestedBid` as a baseline when setting bids for new items.
- Definition of all columns: https://developer.walmart.com/advertising-partners-search/docs/definition-of-columns-in-advanced-insights-report
