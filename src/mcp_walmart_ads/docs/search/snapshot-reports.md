# Snapshot Reports API (Sponsored Search)

## Performance report snapshot

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/create-report-snapshot-updated
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-snapshot-v2-reports-updated
- https://developer.walmart.com/advertising-partners-search/docs/sample-requests-for-create-report-snapshot-updated
- https://developer.walmart.com/advertising-partners-search/docs/sample-responses-for-create-snapshot-requests-updated
- https://developer.walmart.com/advertising-partners-search/docs/parameters-generated-by-snapshot-reports-v2-updated
- https://developer.walmart.com/advertising-partners-search/docs/report-type-availability-for-snapshot-v2-endpoint-campaign-type-and-advertiser-type-updated
- https://developer.walmart.com/advertising-partners-search/docs/applicable-placements-for-campaign-types-auto-bidded-keyword-bidded-sponsored-brands-and-sponsored-videos-updated

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

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/create-entity-snapshot
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-campaign-entity-snapshots
- https://developer.walmart.com/advertising-partners-search/docs/sample-requests-for-create-entity-snapshot
- https://developer.walmart.com/advertising-partners-search/docs/sample-responses-for-create-entity-snapshot
- https://developer.walmart.com/advertising-partners-search/docs/create-entity-snapshot-brand-asset-manager
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-campaign-entity-brand-asset-manager

### Request entity snapshot

```
POST /api/v1/snapshot/entity
```

Query params:
- `advertiserId` (integer, required) — advertiser identifier
- `entityStatus` (string, required) — `enabled`, `disabled`, or `all` (default: `enabled`)
- `entityTypes` (string array, required) — one or more of: `campaign`, `adGroup`, `keyword`, `adItem`, `bidMultiplier`, `placement`, `sbaProfile`, `adGroupMedia`, `category`, `brandAsset`
- `format` (string, optional) — `gzip` or `zip` (default: `zip`)

Entity type notes:
- `placement` — returns included/excluded placements per campaign
- `sbaProfile` — Sponsored Brands campaigns only
- `adGroupMedia` — Sponsored Video campaigns only
- `category` — Sponsored Brand campaigns only
- `brandAsset` — returns empty when `entityStatus` is `disabled`; response includes associated ad groups and review statuses

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

Output is JSON in zip/gzip containing arrays: `campaigns`, `adGroups`, `keywords`, `adItem`, `placementBidMultipliers`, `platformBidMultipliers`, `sbaProfiles`, `adGroupMedias`, `brandAssets`. Files expire after one day.

## Item recommendations snapshot

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/place-a-request-for-item-recommendations
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-recommendations-snapshots
- https://developer.walmart.com/advertising-partners-search/docs/definition-of-columns-in-the-item-recommendations-reports

### Request item recommendations

```
POST /api/v1/snapshot/recommendations
```

Query params:
- `advertiserId` (integer, required)
- `recommendationType` (string, required) — `itemRecommendations`
- `format` (string, required) — `gzip` or `zip`

Response: `{ "code": "success", "snapshotId": "...", "jobStatus": "pending" }`

Retrieve using `GET /api/v1/snapshot` with `advertiserId` and `snapshotId`.

### Output columns

`reportDate`, `itemId`, `itemName`, `suggestedBid`, `brandName`, `superDepartmentName`, `departmentName`, `category`, `subCategory`. Taxonomy fields may be blank depending on site taxonomy.

## Keyword recommendations snapshot

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/overview-15
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-recommendations-snapshots-1
- https://developer.walmart.com/advertising-partners-search/docs/definition-of-columns-in-the-keyword-recommendations-reports

### Request keyword recommendations

```
POST /api/v1/snapshot/recommendations
```

Query params:
- `advertiserId` (integer, required)
- `recommendationType` (string, required) — `keywordRecommendations`
- `format` (string, required) — `gzip` or `zip`

Response: `{ "code": "success", "snapshotId": "...", "jobStatus": "pending" }`

Retrieve using `GET /api/v1/snapshot` with `advertiserId` and `snapshotId`.

Eligibility: ad groups must be live for at least 3 days. Manual bidding campaigns only. Up to 40 keywords per ad group. Updated daily.

### Output columns

Standard: `reportDate`, `campaignId`, `campaignName`, `adGroupId`, `adGroupName`, `keywordText`, `suggestedBid`.

Match type variant adds: `matchType` (`exact`, `phrase`, `broad`).

## Campaign recommendations snapshot (out of budget)

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/create-campaign-recommendations-request
- https://developer.walmart.com/advertising-partners-search/docs/retrieve-campaign-recommendations-snapshot

### Request campaign recommendations

```
POST /api/v2/snapshot/recommendations
```

Body:
- `advertiserId` (integer, required)
- `recommendationType` (string, required) — `outOfBudget`
- `format` (string, required) — `gzip`
- `reportMetrics` (array, required) — metrics to include in the report

Available metrics: `startDate`, `endDate`, `campaignId`, `budgetType` (`daily`/`both`), `missedClicksLower`, `missedClicksUpper`, `missedImpressionsLower`, `missedImpressionsUpper`, `avgCapOutTime` (military time), `suggestedLatestDailyBudget`, `suggestedLatestTotalBudget`.

Response: `{ "code": "success", "snapshotId": "...", "jobStatus": "pending" }`

Retrieve using `GET /api/v2/snapshot` with `advertiserId` and `snapshotId`.

Reports campaigns that went out-of-budget for T-1. Missed clicks/impressions are cumulative over last 7 days. Budget suggestions are latest values, not cumulative. Updated once per 24-hour cycle.

## Insight snapshot (advertiser attributes)

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/advertiser-attributes-snapshot-overview
- https://developer.walmart.com/advertising-partners-search/docs/create-advertiser-attributes-snapshot
- https://developer.walmart.com/advertising-partners-search/docs/definition-of-various-parameters-generated-across-the-advertiser-attributes-snapshot-reports

### Request insight snapshot

```
POST /api/v1/snapshot/insight
```

Body:
- `insightType` (string, required) — `advertiserAttributes` or `advertiserAttributesV2`
- `format` (string, required) — `zip` or `gzip`

Response:
- `code` (string) — `success` or `failure`
- `snapshotId` (string)
- `details` (string) — error details on failure
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed` | `expired`

Retrieve using `GET /api/v1/snapshot` with `advertiserId` and `snapshotId`.

### Output fields — advertiserAttributes

`advertiserId`, `advertiserName`, `advertiserType` (`1p`/`3p`), `sellerId`, `sellerName`, `apiAccessType` (read/write), `accessGrantTimeStamp`, `accountSpendLimitReached` (`1`/`0`, 3p only), `reportDate`.

### Output fields — advertiserAttributesV2

All fields from v1 plus: `organizationId`, `organizationName`, `approvedBrandNames` (list — brands eligible for SBA/SV), `advertiserAccess` (list of objects with `resourceGroupName`, `permissionType`, `grantTimeStamp`).

Resource group names: `REPORTING`, `CAMPAIGN_MANAGER`, `CREATIVE_HUB`. Permission types: `Edit`, `View Only`.

## Notes

- Snapshot IDs expire 24 hours after generation.
- No limit on number of snapshot requests per advertiser.
- Large responses are truncated in the tool result; full data available via `wmc://responses/{request_id}`.
