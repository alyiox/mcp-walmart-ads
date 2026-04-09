# Keywords API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/reference/

## List keywords

```
GET /api/v1/keywords
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)
- `adGroupId` (integer, optional)

## Create keywords

```
POST /api/v1/keywords?advertiserId={advertiserId}
```

Body: JSON array of keyword objects.

Fields:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `adGroupId` (integer, required)
- `keyword` (string, required)
- `matchType` (string, required) — `exact` | `phrase` | `broad`
- `bid` (number, optional)
- `status` (string) — `enabled` | `disabled`

## Update keywords

```
PUT /api/v1/keywords?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `keywordId` plus fields to update.

## Delete keywords

```
PUT /api/v1/keywords/delete
```

Body: JSON array of `{ "keywordId": integer }`.

## Notes

- Max 50 entities per POST/PUT batch.
- Same keyword with different match types counts as separate entries.
- Max 1000 keyword-match type combinations per ad group.
