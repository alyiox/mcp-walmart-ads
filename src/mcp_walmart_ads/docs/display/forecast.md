# Forecast API (Display)

Reference: https://developer.walmart.com/advertising-partners/docs/request-reach-estimate-v2

Provides reach and delivery estimates before launching or modifying ad groups. Use to validate budget, bid, and targeting configurations.

## Reach estimate

Estimates the potential audience size (impressions) for a targeting configuration.

### Reach estimate v2 (recommended)

```
POST /api/v2/reachEstimate
```

Body:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `adGroupId` (integer, required)
- `metric` (array, required) — currently only `"impressions"`
- `startDate` (datetime ISO 8601, optional) — simulated start; normalized to ET hour
- `endDate` (datetime ISO 8601, optional) — must be after 12:00 PM ET
- `targeting` (object, conditional) — required if not configured at ad group level:
  - `keywords`, `contextual`, `behavioral`, `runOfSite`, `geoTargets`
- `timeframes` (array, optional) — `"daily"` | `"30days"` | `"lifetime"`

Response:
- `code` (string) — `success` or `failure`
- `forecastId` (string)
- `estimates.impressions.{daily|30days|lifetime}`:
  - `minValue` (integer)
  - `maxValue` (integer) — omitted if unbounded
  - `scale` (string) — `LOW` | `MODERATE` | `HIGH`
- `details` (array)

### Reach estimate v1

```
POST /api/v1/reachEstimate
```

Same parameters as v2. Use v2 for new integrations.

## Delivery estimate

Estimates impressions, clicks, spend, and orders for a given configuration and budget.

### Delivery estimate v2 (recommended)

```
POST /api/v2/deliveryEstimate
```

Body:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `adGroupId` (integer, required)
- `metric` (array, required) — one or more of: `impressions`, `clicks`, `adSpend`, `orders`
- `timeframes` (array, optional) — `"daily"` | `"30days"` | `"lifetime"`
- `startDate` (datetime ISO 8601, conditional) — normalized to ET hour
- `endDate` (datetime ISO 8601, conditional) — must be after 12:00 PM ET
- `targeting` (object, conditional) — required if not configured at ad group level
- `maxBid` (double, conditional) — min $0.01
- `baseBid` (double, conditional) — min $0.01
- `dailyBudget` (double, conditional) — min $0.01
- `totalBudget` (double, conditional) — min $0.01
- `deliverySpeed` (string, conditional) — `frontloaded` or `evenly`
- `frequencyCapDay` (integer, optional) — 1–511
- `frequencyCapWeek` (integer, optional) — 3–511
- `frequencyCapMonth` (integer, optional) — 5–511

Response:
- `code` (string) — `success`, `failure`, or `partial_response`
- `forecastId` (string)
- `estimates.{metric}.{timeframe}`:
  - `minValue` (integer)
  - `maxValue` (integer) — omitted if unbounded
- `details` (array)
- `errors` (array) — populated on `partial_response`

### Delivery estimate v1

```
POST /api/v1/deliveryEstimate
```

Subset of v2 metrics (impressions only). Use v2 for new integrations.

## Notes

- Conditional fields are required only if not already configured at the ad group level.
- Estimates are probabilistic ranges, not guarantees.
