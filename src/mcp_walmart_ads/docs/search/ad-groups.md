# Ad Groups API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/reference/

## List ad groups

```
GET /api/v1/adGroups
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)
- `filter[name]` (string, optional)
- `filter[lastModifiedDate]` (date `yyyy-MM-dd`, optional)

## Create ad groups

```
POST /api/v1/adGroups?advertiserId={advertiserId}
```

Body: JSON array of ad group objects.

Fields:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `name` (string, required, max 255 chars)
- `status` (string) — `enabled` | `disabled`
- `defaultBid` (number, optional)

## Update ad groups

```
PUT /api/v1/adGroups?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `adGroupId` plus fields to update.

## Delete ad groups

```
PUT /api/v1/adGroups/delete
```

Body: JSON array of `{ "adGroupId": integer }`.

## Notes

- Max 50 entities per POST/PUT batch.
- Max 2000 items per ad group.
- Max 1000 keyword-match type combinations per ad group.
- Max 15000 ad groups per advertiser account.
- SBA campaigns: only one ad group allowed per campaign.
