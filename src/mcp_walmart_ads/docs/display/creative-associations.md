# Ad Group Creative Associations API (Display)

Reference: https://developer.walmart.com/advertising-partners/docs/add-creatives-to-ad-groups

Associates approved creatives with ad groups. An ad group must have at least one approved creative to go live.

## Add creative to ad group

```
POST /api/v1/adGroupCreativeAssociations
```

Batch: max 5 per request; all must share the same `advertiserId`.

Body:
- `advertiserId` (integer, required)
- `adGroupId` (integer, required)
- `creativeId` (string, required)
- `urlTracker` (array, required) — one object per ad unit

### urlTracker object fields

- `adUnit` (string, required) — `SKYLINE` | `MARQUEE` | `GALLERY` | `BRANDBOX` | `TILE`
- `clickUrlDesktopMWeb` (string, required) — Walmart.com hosted click URL for desktop/mWeb
- `clickUrlApp` (string, required) — Walmart.com hosted click URL for app
- `dcmClickUrlDesktopMWeb` (string, optional) — DCM click tracker for desktop/mWeb
- `dcmClickUrlApp` (string, optional) — DCM click tracker for app
- `dcmImprUrlDesktopMWeb` (string, optional) — DCM impression tracker desktop/mWeb
- `dcmImprUrlApp` (string, optional) — DCM impression tracker app
- `iasImprUrlDesktopMWeb` (string, optional) — IAS impression tracker desktop/mWeb
- `iasImprUrlApp` (string, optional) — IAS impression tracker app
- `dvImprUrlDesktopMWeb` (string, optional) — DV impression tracker desktop/mWeb
- `dvImprUrlApp` (string, optional) — DV impression tracker app
- `iasDesktopMWebTag` (string, optional) — IAS IVT/viewability tag
- `dvDesktopMWebTag` (string, optional) — DV IVT/viewability tag

Additional body fields:
- `badgeSettings` (array, optional) — badge config objects:
  - `type` (string) — `ROLLBACK` or `EXPRESS_DELIVERY`
  - `enabled` (boolean, optional, default: true)
- `showPrice` (boolean, optional, default: false) — display item price; requires exactly 1 `associatedItems` entry
- `associatedItems` (array, optional) — item IDs to link, max 5

Response:
- `code` (string) — `success` or `failure`
- `adGroupId` (integer)
- `creativeId` (string)
- `details` (array) — per-ad-unit success/error messages

## List creative associations

```
POST /api/v1/adGroupCreativeAssociations/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[adGroupId]` (array, optional)
- `Filter[creativeId]` (array, optional)
- `startIndex` (integer, optional)
- `count` (integer, optional)

## Update creative association

```
PUT /api/v1/adGroupCreativeAssociations
```

Body: JSON array. Each object must include `adGroupId` and `creativeId` plus fields to update (`urlTracker`, `badgeSettings`, `showPrice`, `associatedItems`).

## Delete creative association

```
DELETE /api/v1/adGroupCreativeAssociations
```

Body:
- `advertiserId` (integer, required)
- `adGroupId` (integer, required)
- `creativeId` (string, required)

## Notes

- Creative must be `APPROVED` or `PENDING_APPROVAL` to associate.
- Cannot modify associations for ad groups in `COMPLETE` status.
- When badges are enabled, `clickUrl` for desktop/mWeb and app must match.
- `showPrice=true` is only valid with exactly 1 `associatedItems` entry.
