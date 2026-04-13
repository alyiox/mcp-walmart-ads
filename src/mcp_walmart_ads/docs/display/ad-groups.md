# Ad Groups API (Display)

Reference: https://developer.walmart.com/advertising-partners/docs/overview-28

Limits: max 5,000 campaigns and 15,000 ad groups per account. Batch max: 10 per request (same `advertiserId`).

## Create ad group

```
POST /api/v1/adGroups
```

Body:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `name` (string, required, max 1024 chars)
- `startDate` (datetime ISO 8601, conditional) — today or later
- `endDate` (datetime ISO 8601, conditional) — use `9999-12-30T00:00:00Z` for indefinite
- `rateType` (string, optional) — `cpm`
- `budgetType` (string, conditional) — `daily` or `total`
- `dailyBudget` (double, conditional) — min $0.01; required when `budgetType=daily`
- `totalBudget` (double, conditional) — min $0.01; required when `budgetType=total`
- `deliverySpeed` (string, conditional) — `frontloaded` or `evenly`
- `baseBid` (double, optional) — starting bid, min $0.01
- `maxBid` (double, optional) — max bid, min $0.01
- `creativeRotationMode` (string, optional) — `OPTIMIZE_PERFORMANCE` (default) or `ROTATE_EVENLY`
- `frequencyCapDay` (integer, optional) — 1–511
- `frequencyCapWeek` (integer, optional) — 3–511
- `frequencyCapMonth` (integer, optional) — 5–511
- `isInventoryAware` (boolean, optional)
- `targeting` (object, optional):
  - `keywords` — array of `{ keywordText, matchType: broad|exact }`
  - `contextual` — array of `{ id, reach: tier_1…tier_7 }`
  - `behavioral` — array of `{ id, audienceType, attribute }`
  - `runOfSite` (boolean)
  - `geoTargets` — array of geo target objects with `id`

Response: `{ "code": "success", "adGroupId": N, "campaignId": N, "name": "..." }`

## List ad groups

```
POST /api/v1/adGroups/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[campaignId]` (integer, optional)
- `Filter[adGroupId]` (array, optional)
- `Filter[lastModifiedDate]` (date `yyyy-MM-dd'T'HH:mm:ss.SSSXXX`, optional)
- `startIndex` (integer, optional)
- `count` (integer, optional)

Response: `{ "totalResults": N, "adGroups": [...] }`

## Update ad group

```
PUT /api/v1/adGroups
```

Body: JSON array. Each object must include `adGroupId` plus fields to update (same fields as create except `campaignId`).

## Update ad group delivery status

```
PUT /api/v1/adGroups/action
```

Body: JSON array (max 10 per batch; all same `advertiserId`).

Fields:
- `advertiserId` (integer, required)
- `adGroupId` (integer, required)
- `action` (string, required) — `PAUSE` | `RESUME` | `ARCHIVE` | `UNARCHIVE`

Action rules:
- `PAUSE` — LIVE ad groups only
- `RESUME` — PAUSED ad groups only
- `ARCHIVE` — DRAFT ad groups that never went live
- `UNARCHIVE` — restores ARCHIVED ad groups to DRAFT

## Keywords

Display ad group keywords are used for keyword targeting (not bid-based like search).

Reference: https://developer.walmart.com/advertising-partners/docs/list-all-the-keywords-in-an-ad-group

### List keywords in ad group

```
POST /api/v1/keywords/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[adgroupId]` (integer, required)
- `Filter[lastModifiedDate]` (date `yyyy-MM-dd'T'HH:mm:ss.SSSXXX`, optional)
- `startIndex` (integer, optional)
- `count` (integer, optional)

Response:
- `totalResults` (integer)
- `adGroupId` (integer)
- `keywords` (array) — objects with `keywordText`, `matchType` (`EXACT`|`BROAD`), `isExcluded` (boolean), `reviewStatus` (`APPROVED`|`REJECTED`|`PENDING REVIEW`)
