# Placements API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/docs/overview-6

## List editable campaign placements

```
GET /api/v1/campaigns/{campaignId}/placements
```

Query params:
- `advertiserId` (integer, required)

Response: array of placement objects with `placementType` and current `status`.

Placement types: `search`, `browse`, `itemPage`, `buyBox`, `homePage`.

## Update campaign placements

```
PUT /api/v1/campaigns/{campaignId}/placements
```

Body: JSON array of placement objects.

Fields:
- `advertiserId` (integer, required)
- `placementType` (string, required) — placement to update
- `status` (string, required) — `included` | `excluded`

## Notes

- Placements control where ads appear on Walmart.com.
- Not all placement types are editable for all campaign types.
- See bid multipliers for per-placement bid adjustments.
