# Audiences API (Display)

Reference:
- https://developer.walmart.com/advertising-partners/docs/create-audience
- https://developer.walmart.com/advertising-partners/docs/update-custom-audience-patch
- https://developer.walmart.com/advertising-partners/docs/get-list-of-audiences-copy
- https://developer.walmart.com/advertising-partners/docs/create-brand-audiences
- https://developer.walmart.com/advertising-partners/docs/retrieve-brand-audiences-status
- https://developer.walmart.com/advertising-partners/docs/audience-size-estimate-api
- https://developer.walmart.com/advertising-partners/docs/audience-intelligence-api-copy
- https://developer.walmart.com/advertising-partners/docs/audience-api-error-codes-and-descriptions

## Create custom audience

```
POST /api/v1/audiences
```

Body:
- `advertiserId` (integer, required)
- `name` (string, required) — max 120 characters, must be unique
- `description` (string, optional) — max 120 characters
- `audienceType` (string, required) — must be `CUSTOM`
- `audienceObjective` (array, required) — values: `REACH`, `PERFORMANCE`, `OTHER`
- `audienceObjectiveText` (string, conditional) — required when objective includes `OTHER`
- `attribute` (string, required) — `ITEM_PROPENSITY`, `RULE_BASED`, `LOOKALIKE`, `BRAND_AFFINITY`, or `ADVANCED`
- `audienceDefinition` (object, required) — contains `audienceCriteria`

Audience criteria by attribute type:

**ITEM_PROPENSITY:**
- `propensityCriteria.strategy` (string)
- `propensityCriteria.itemsetIds` (array of integers) — OR `propensityCriteria.categories` (not both); itemsets must be in `BUILT` status

**RULE_BASED:**
- `include` (object) — `purchaseCriteria` and/or `browseCriteria`
- `exclude` (object, optional)
- `demographics` (object, optional) — `gender`, `ageRange`, `income`; age/income ranges must be continuous (no gaps)
- `geoTargets` (array, optional) — objects with `id` or `zipcode`

Purchase offset values: 1, 7, 30, 90, 182, 365, 730, 1095, 1460, 1825 days. Cannot mix offset days with offset dates in same request.

**LOOKALIKE:**
- `lookAlikeCriteria.seedAudienceId` (integer) — seed must have 50,000+ users, built within 30 days or used in active campaign

**BRAND_AFFINITY:**
- `brandAffinityCriteria.brands` (array of strings)
- `brandAffinityCriteria.brandAffinityType` (string) — `BRAND_SWITCHERS`, `BRAND_LOYALISTS`, or `BRAND_PROSPECTS`
- `brandAffinityCriteria.categories` (array) — hierarchical category objects (levels 1–3 required)

**ADVANCED:**
- `advancedCriteria.include` (array, required) — array of `matchAny` groups
- `advancedCriteria.exclude` (array, optional) — array of `matchAny` groups

Response: `{ "code": "success", "audienceId": 123, "name": "...", "details": ["..."] }`

Audience building is async and may take hours depending on size.

## Update custom audience

```
PATCH /api/v1/audiences
```

Body:
- `advertiserId` (integer, required)
- `audienceId` (integer, required)
- `name` (string, optional) — max 120 characters, must be unique
- `description` (string, optional) — max 120 characters
- `attribute` (string, conditional) — required when updating `audienceDefinition`; `ITEM_PROPENSITY` or `RULE_BASED`
- `audienceObjective` (array, optional) — values: `REACH`, `PERFORMANCE`, `OTHER`
- `audienceObjectiveText` (string, conditional) — required when objective includes `OTHER`
- `audienceDefinition` (object, optional) — contains `audienceCriteria` (same structure as create)

Updating `audienceDefinition` overwrites the existing definition and triggers automatic rebuild (status transitions to `IN_PROGRESS`).

Response: `{ "code": "success", "audienceId": 123, "name": "...", "details": ["AUDIENCE_UPDATE_SUCCESS"] }`

## List custom audiences

```
POST /api/v1/audiences/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[audienceId]` (array, optional) — max 10 IDs
- `Filter[name]` (string, optional) — max 5 names
- `Filter[status]` (string, optional) — `AVAILABLE`, `IN_PROGRESS`, `UNAVAILABLE`, `ARCHIVED`
- `Filter[role]` (string, optional) — `owned` or `shared` (default: both)
- `startIndex` (integer, optional) — pagination offset
- `count` (integer, optional) — results per page (default: 100)

Response: `{ "totalResults": N, "data": [...] }`

Audience object fields: `audienceId`, `audienceType`, `attribute`, `name`, `status`, `size` (with `min`/`max`), `creationDate`, `lastUpdatedDate`, `statusDesc`, `audienceDefinition`, `audienceCriteria`, `isShared`, `audienceObjective`, `audienceObjectiveText`, `source`.

## Create brand audience

```
POST /api/v1/audiences/brand
```

Body:
- `advertiserId` (integer, required)
- `name` (string, required) — brand name
- `audienceType` (string, required) — must be `BRAND`
- `attribute` (array of strings, required) — values: `HISTORICAL`, `PREDICTIVE`, `LAPSED_BUYERS`

Response: `{ "code": "success", "requestId": 1234, "details": ["BRAND_AUDIENCE_CREATE_REQUEST_SUCCESS"] }`

Processing is async — use the brand audience status endpoint to poll completion.

## Get brand audience status

```
GET /api/v1/audiences/brand/status
```

Query params:
- `advertiserId` (integer, required)
- `requestId` (string, required) — from the create brand audience response

Response:
- `name` (string) — brand name
- `audiencesRequested` (integer) — number of audiences requested (max 3)
- `jobStatus` (string) — `IN_PROGRESS` or `COMPLETED`
- `audienceInfo` (array) — objects with `audienceId` (integer) and `audienceAttribute` (`HISTORICAL`, `PREDICTIVE`, or `LAPSED_BUYERS`)

Fewer results than requested may indicate processing is still underway. Created audiences are ready for targeting even while still building.

## Audience size estimate

```
POST /api/v1/audiences/estimate
```

Two approaches (do not combine in one request):

**By existing audience:**
- `advertiserId` (integer, required)
- `audienceId` (integer, required)
- `date` (string, optional) — ISO format `yyyy-MM-dd`; defaults to current ET date

**By audience definition:**
- `advertiserId` (integer, required)
- `audienceType` (string, required) — `CUSTOM`
- `attribute` (string, required) — `RULE_BASED` or `ADVANCED`
- `audienceDefinition` (object, required) — same structure as create
- `date` (string, optional) — ISO format `yyyy-MM-dd`

Response: `{ "audienceId": 123, "min": 100000000, "max": 100000000, "lastUpdatedAt": "2024-06-27T20:00:00.000-04:00" }`

Advanced audience definitions require seed audiences with `AVAILABLE` status built within 40 days or used in active campaigns.

## Audience intelligence

```
POST /api/v1/audiences/intelligence
```

Body:
- `advertiserId` (integer, required)
- `audienceId` (integer, required)
- `asOfDate` (string, optional) — ISO format `yyyy-MM-dd`; defaults to today
- `dimension` (string, optional) — `AGE`, `GENDER`, `INCOME`, `DMA`, `REGION`, `RESIDENTIAL_STATUS`
- `dmaLimit` (integer, optional) — top DMAs to return (default: 5); only valid with `dimension=DMA`

Response:
- `audienceId` (integer)
- `asOfDate` (string)
- `metrics` (array) — objects with `dimension` and `values` array
- `lastUpdatedAt` (string) — ISO 8601 with timezone

Values array entries: `{ "key": "...", "value": N, "unit": "PERCENT" }`

Key mappings by dimension:

| Dimension | Keys |
|-----------|------|
| AGE | A (18–24), B (25–34), C (35–44), D (45–54), E (55–64), F (65+), U (unknown) |
| GENDER | M (male), F (female), U (unknown) |
| INCOME | A–G (income brackets), U (unknown) |
| REGION | MIDWEST, NORTHEAST, SOUTH, WEST, U (unknown) |
| RESIDENTIAL_STATUS | HOME_OWNER, RENTER, U (unknown) |
| DMA | Market area names from geo locations endpoint |
