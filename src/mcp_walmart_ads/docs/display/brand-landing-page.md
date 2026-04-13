# Brand Landing Page API (Display)

Reference: https://developer.walmart.com/advertising-partners/docs/list-brand-landing-page

Lists brand shop and shelf pages on Walmart.com. Use to find valid landing page URLs for creatives.

## List brand landing pages

```
POST /api/v1/brand-landing-pages/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[itemsetIds]` (array, optional) — filter by associated itemset IDs; max 25
- `Filter[pageType]` (string, optional) — `brand` or `shelf`
- `Filter[pageTitle]` (string, optional)
- `Filter[brandName]` (string, optional)
- `startIndex` (integer, optional, default: 0)
- `count` (integer, optional, default: 100, max: 100)

Response:
- `code` (string) — `success` or `failure`
- `totalResults` (integer)
- `pages` (array):
  - `pageId` (string)
  - `pageUrl` (string) — brand shop or shelf page URL
  - `advertisingUrl` (string) — recommended URL to use as click destination in creatives
  - `pageTitle` (string)
  - `pageType` (string) — `brand` or `shelf`
  - `brandName` (string)
  - `itemsetId` (string) — associated itemset ID
- `details` (array) — error messages on failure

## Notes

- Use `advertisingUrl` (not `pageUrl`) as the click URL in creative `urlTracker` objects.
- Brand pages (`pageType=brand`) are the advertiser's main brand shop.
- Shelf pages (`pageType=shelf`) are category or promotional shelf pages.
