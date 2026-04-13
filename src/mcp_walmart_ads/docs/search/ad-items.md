# Ad Items API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/docs/overview-3

## Add item to ad group

```
POST /api/v1/adItems?advertiserId={advertiserId}
```

Body: JSON array of ad item objects.

Fields:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `adGroupId` (integer, required)
- `itemId` (integer, required) — Walmart item ID
- `status` (string) — `enabled` | `disabled`
- `bid` (number, optional) — item-level bid override

## List items in a campaign

```
GET /api/v1/adItems
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)
- `adGroupId` (integer, optional)

## Update ad item

```
PUT /api/v1/adItems?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `adItemId` plus fields to update (`status`, `bid`).

## Notes

- Max 50 entities per POST/PUT batch.
- Max 2000 items per ad group.
- Item-level bids override the ad group default bid.
- For variant bidding best practices see: https://developer.walmart.com/advertising-partners-search/docs/variant-bidding-best-practices
