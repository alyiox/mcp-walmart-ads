# Bid Multipliers API (Sponsored Search)

Reference: https://developer.walmart.com/advertising-partners-search/docs/overview-13

Bid multipliers adjust bids up or down for specific placements or platforms without changing the base bid.

## Placement Bid Multipliers

Adjust bids by placement (where the ad appears on Walmart.com).

Placement types: `search`, `browse`, `itemPage`, `buyBox`, `homePage`.

### Create placement bid multipliers

```
POST /api/v1/placementBidMultipliers?advertiserId={advertiserId}
```

Body: JSON array.

Fields:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `placementType` (string, required)
- `multiplier` (number, required) — e.g. `1.5` = +50%, `0.8` = -20%

### List placement bid multipliers

```
GET /api/v1/placementBidMultipliers
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)

### Update placement bid multipliers

```
PUT /api/v1/placementBidMultipliers?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `placementBidMultiplierId` plus `multiplier` to update.

## Platform Bid Multipliers

Adjust bids by device platform.

Platform types: `desktop`, `mobile`, `app`.

### Create platform bid multipliers

```
POST /api/v1/platformBidMultipliers?advertiserId={advertiserId}
```

Body: JSON array.

Fields:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `platformType` (string, required)
- `multiplier` (number, required)

### List platform bid multipliers

```
GET /api/v1/platformBidMultipliers
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)

### Update platform bid multipliers

```
PUT /api/v1/platformBidMultipliers?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `platformBidMultiplierId` plus `multiplier` to update.

## Notes

- Multiplier of `1.0` means no adjustment.
- Multipliers apply on top of the keyword or item-level bid.
- Placement and platform multipliers stack multiplicatively.
