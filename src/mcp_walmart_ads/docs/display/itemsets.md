# Itemsets API (Display)

Reference:
- https://developer.walmart.com/advertising-partners/docs/create-itemsets-copy
- https://developer.walmart.com/advertising-partners/docs/list-itemsets
- https://developer.walmart.com/advertising-partners/docs/update-itemsets
- https://developer.walmart.com/advertising-partners/docs/itemsets-info-1
- https://developer.walmart.com/advertising-partners/docs/itemset-expression

## Create itemset

```
POST /api/v1/itemset
```

Body:
- `advertiserId` (integer, required)
- `name` (string, required)
- `type` (string, required) — `item`, `brand`, `category`, or `hybrid`
- `description` (string, optional)
- `class` (string, optional) — `measurement` (default) or `targeting`
- `editable` (string, optional) — `true`
- `itemsetType` (string, optional) — measurement class only: `featured` (default) or `halo`
- `items` (array, conditional) — when `type=item` and no expression; objects with `id` (string) and `itemType` (`gtin`, `upc`, `stores`, `online`)
- `brands` (array of strings, conditional) — when `type=brand` and no expression
- `expression` (object, conditional) — when neither items nor brands provided; logical OR of item/brand/category clauses

Expression structure:
```json
{ "or": [{ "type": "item|brand|category", "value": {...} }] }
```

Value by type:
- item: `{ "itemId": "...", "itemType": "gtin|upc|stores|online" }`
- brand: `{ "name": "..." }`
- category: `{ "name": "...", "level": 1|2|3, "attributes": [{ "type": "...", "values": [...] }] }`

Response: `{ "code": "success", "itemsetId": 123 }`

Async — use list endpoint to verify build status. For UNIVERSAL catalog items use GTIN as `itemType`. Featured itemsets support only item-based content. Halo itemsets support items, brands, categories, or hybrid.

## List itemsets

```
POST /api/v1/itemsets/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[itemsetId]` (array, optional) — max 25 IDs
- `Filter[lastModifiedDate]` (date, optional) — format: `yyyy-MM-dd'T'HH:mm:ss.SSSXXX`
- `Filter[class]` (string, optional) — `measurement` or `targeting`
- `Filter[status]` (string, optional) — `DRAFT`, `PENDING`, `BUILDING`, `FAILED`, `BUILT`, `INVALID`
- `Filter[role]` (string, optional) — `owned` (default) or `shared`
- `startIndex` (string, optional) — pagination offset (0-based)
- `count` (integer, optional) — results per page (default/max: 100)

Response: `{ "code": "success", "totalResults": N, "itemsets": [...] }`

Itemset object fields: `itemsetId`, `name`, `description`, `status`, `class` (`MEASUREMENT`/`TARGETING`), `editable`, `creationDate`, `lastUpdatedDate`, `itemsetType` (`FEATURED`/`HALO`), `haloType` (`BRAND`/`CATEGORY`/`CUSTOM`/`NONE`), `parentFeaturedItemsetId`, `type`, `source`, `isShared`.

Shared itemsets have `editable=false` and cannot be updated. Halo itemsets are auto-generated and non-editable.

## Update itemset

```
PUT /api/v1/itemset
```

Body:
- `advertiserId` (integer, required)
- `itemsetId` (integer, required)
- `type` (string, required) — `item`, `brand`, `category`, or `hybrid`
- `name` (string, optional)
- `description` (string, optional)
- `items` / `brands` / `expression` (conditional) — same structure as create

PUT overwrites all current values (no incremental updates). Only `name`, `description`, and item/brand/category lists can be updated. Class and type are immutable. Itemset must be in `BUILT` or `INVALID` status. Auto-generated halo itemsets cannot be updated.

Response: `{ "code": "success", "itemsetId": 123 }`

## Get itemset info

```
POST /api/v1/itemset/info
```

Body:
- `advertiserId` (integer, required)
- `Filter[itemsetId]` (integer, required) — single ID
- `showItems` (boolean, optional) — for brand itemsets: `false` returns brands, `true` returns items (up to 10,000); always `true` for item/category/hybrid
- `startIndex` (integer, optional) — pagination offset
- `count` (integer, optional) — results per page (default/max: 100)

Response: `{ "code": "success", "itemsetId": N, "totalResults": N, "items": [...], "brands": [...] }`

Metadata may take 3–5 minutes to become available after creation.

## Get itemset expression

```
POST /api/v1/itemset/expression
```

Body:
- `advertiserId` (integer, required)
- `Filter[itemsetId]` (integer, required) — single ID

Response: `{ "code": "success", "expression": { "or": [...] } }`

Expression entries have type `ITEMSET` (child itemset with `id`), `BRAND` (with `name`), or `CATEGORY` (with `name`, `level`, `attributes`). Only successfully built itemsets return data.
