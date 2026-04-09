# Campaigns API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/reference/

## List campaigns

```
GET /api/v1/campaigns
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional) — filter by ID
- `filter[name]` (string, optional) — filter by name
- `filter[lastModifiedDate]` (date `yyyy-MM-dd`, optional)

Response: array of campaign objects.

## Create campaigns

```
POST /api/v1/campaigns?advertiserId={advertiserId}
```

Body: JSON array of campaign objects.

Fields:
- `advertiserId` (integer, required)
- `name` (string, required)
- `campaignType` (string) — `sponsoredProducts` | `sba` | `video`
- `status` (string) — `enabled` | `disabled`
- `targetingType` (string) — `manual` | `auto`
- `startDate` (date `yyyy-MM-dd`, required)
- `endDate` (date `yyyy-MM-dd`, optional)
- `dailyBudget` (number, optional)
- `totalBudget` (number, optional)
- `budgetType` (string) — `daily` | `total` | `both`
- `rollover` (boolean, optional)
- `biddingStrategy.strategy` (string) — `DYNAMIC` | `FIXED` | `TROAS`

## Update campaigns

```
PUT /api/v1/campaigns?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `campaignId` plus fields to update.

## Delete campaigns

```
PUT /api/v1/campaigns/delete
```

Body: JSON array of `{ "campaignId": integer }`. Only campaigns that have never gone live can be deleted.

## Notes

- Max 50 entities per POST/PUT batch.
- Once a campaign goes live, start/end dates cannot be changed and it cannot be deleted.
