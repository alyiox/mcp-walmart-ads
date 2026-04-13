# Top Search Trends API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/docs/overview-16

Provides a snapshot of trending search terms on Walmart.com. Use to discover high-volume keywords for campaign targeting.

## Request top search trends snapshot

```
POST /api/v1/snapshot/insight
```

Body:
- `insightType` (string, required) — `topSearchTrends`
- `format` (string, required) — `zip` or `gzip`

Response:
- `code` (string) — `success` or `failure`
- `snapshotId` (string)
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`

Retrieve using `GET /api/v1/snapshot` with `advertiserId` and `snapshotId`.

## Report format

Output is CSV (compressed). Columns:

- `searchTerm` — trending search keyword
- `searchVolume` — relative search frequency
- `searchRank` — rank among trending terms
- `department` — top associated department
- `category` — top associated category
- `reportDate` — date the snapshot was generated

## Notes

- Updated daily; reflects trends from the prior day.
- Use `searchTerm` values directly when adding keywords via the Keywords API.
- See recommended practices: https://developer.walmart.com/advertising-partners-search/docs/recommended-best-practices-and-actions
