# Catalog Item Search API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/docs/overview-12

Searches the Walmart.com published item catalog. Use to find item IDs before adding them to ad groups.

## Search items

```
GET /api/v1/itemSearch
```

Query params:
- `advertiserId` (integer, required)
- `keyword` (string, optional) — search term
- `itemId` (integer, optional) — filter by specific item ID
- `limit` (integer, optional) — max results per page
- `offset` (integer, optional) — pagination offset

Response: array of item objects.

Item object fields:
- `itemId` (integer) — Walmart item ID
- `itemName` (string) — item title
- `brandName` (string)
- `price` (number)
- `itemPageUrl` (string)
- `primaryImageUrl` (string)
- `publishedStatus` (string) — `published` | `unpublished`

## Notes

- Only published items can be added to ad groups.
- Use `itemId` to add items via the Ad Items API.
