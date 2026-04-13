# Catalog API (Display)

Reference:
- https://developer.walmart.com/advertising-partners/docs/list-items
- https://developer.walmart.com/advertising-partners/docs/list-brands
- https://developer.walmart.com/advertising-partners/docs/retrieve-list-of-taxonomies

Browse the Walmart item catalog, brands, and taxonomy for building itemsets and targeting configurations.

## List items

```
POST /api/v1/items/list
```

Body:
- `advertiserId` (integer, required)
- `isRestricted` (boolean, optional) — `true` = own catalog only (default); `false` = all available items
- `filter[itemId]` (array, optional) — specific item IDs
- `filter[itemName]` (array, optional) — exact name match; required when `isRestricted=false`
- `filter[catalog]` (string, optional) — `online` | `stores` | `universal`
- `filter[gtin]` (array, optional) — GTIN values
- `filter[department]` (array, optional) — department names (case-insensitive, exact)
- `filter[category]` (array, optional) — category names (case-insensitive, exact)
- `filter[subCategory]` (array, optional) — subcategory names (case-insensitive, exact)
- `filter[brandName]` (array, optional) — brand names (exact)
- `filter[itemType]` (string, optional) — `base` or `variant`
- `expandVariants` (boolean, optional, default: false) — return base + variants when filtering by `itemId`/`gtin`
- `startIndex` (integer, optional, default: 0)
- `count` (integer, optional, default: 100)

Response:
- `code` (string)
- `totalResults` (integer)
- `data` (array):
  - `catalog` — `ONLINE` | `STORES` | `UNIVERSAL`
  - `itemId` (integer)
  - `gtin` (string)
  - `itemName` (string)
  - `imageUrl` (string)
  - `itemPageUrl` (string)
  - `brandName` (string)
  - `department` (string)
  - `category` (string)
  - `subCategory` (string)
  - `baseItemId` (integer) — `-1` for regular items

## List brands

```
POST /api/v1/brands/list
```

Body:
- `advertiserId` (integer, required)
- `filter[brandName]` (array, optional) — brand name filter
- `startIndex` (integer, optional)
- `count` (integer, optional)

Response:
- `totalResults` (integer)
- `brands` (array) — objects with `brandName`

## List taxonomies

```
POST /api/v1/taxonomies/list
```

Body:
- `advertiserId` (integer, required)
- `filter[department]` (string, optional)
- `filter[category]` (string, optional)
- `startIndex` (integer, optional)
- `count` (integer, optional)

Response:
- `totalResults` (integer)
- `taxonomies` (array) — hierarchical objects with `department`, `category`, `subCategory`

## Notes

- Use `itemId` values when creating item-based itemsets.
- Use `gtin` for UNIVERSAL catalog items in itemsets (`itemType: "gtin"`).
- Taxonomy values are used in itemset category expressions and audience category criteria.
