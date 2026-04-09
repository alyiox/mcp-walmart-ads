# Campaigns API (Display)

Reference: https://developer.walmart.com/advertising-partners/reference/

## Campaign Groups

### Create campaign group

```
POST /api/v1/campaignGroups
```

Body:
- `advertiserId` (integer, required)
- `name` (string, required)
- `status` (string) — `enabled` | `disabled`
- `startDate` (date `yyyy-MM-dd`, required)
- `endDate` (date `yyyy-MM-dd`, optional)
- `budget` (number, optional)

### List campaign groups

```
GET /api/v1/campaignGroups
```

Query params:
- `advertiserId` (integer, required)

### Update campaign group

```
PUT /api/v1/campaignGroups
```

Body: array with `campaignGroupId` plus fields to update.

## Line Items

### Create line item

```
POST /api/v1/lineItems
```

Body:
- `advertiserId` (integer, required)
- `campaignGroupId` (integer, required)
- `name` (string, required)
- `status` (string) — `enabled` | `disabled`
- `startDate` (date `yyyy-MM-dd`, required)
- `endDate` (date `yyyy-MM-dd`, optional)
- `budget` (number, optional)
- `bidAmount` (number, optional)

### List line items

```
GET /api/v1/lineItems
```

Query params:
- `advertiserId` (integer, required)
- `campaignGroupId` (integer, optional)

### Update line item

```
PUT /api/v1/lineItems
```

Body: array with `lineItemId` plus fields to update.
