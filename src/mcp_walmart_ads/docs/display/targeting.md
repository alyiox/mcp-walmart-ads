# Targeting API (Display)

## Contextual and behavioral targets

Reference:
- https://developer.walmart.com/advertising-partners/docs/list-of-contextual-and-behavioral-targets-in-a-campaign

### List targets

```
POST /api/v2/targeting/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[tactic]` (string, required) — `contextual` or `behavioral`
- `Filter[id]` (array, optional) — specific target/audience IDs
- `Filter[audienceType]` (string, conditional) — required for behavioral unless `Filter[id]` or `searchText` provided; one of: `retail`, `brand`, `custom`, `persona`, `demographic`
- `Filter[attribute]` (string, conditional) — varies by audience type (see below)
- `searchText` (string, optional) — search query
- `startIndex` (integer, optional) — pagination offset
- `count` (integer, optional) — number of results

Attribute mappings by audience type:

| audienceType | attributes |
|--------------|------------|
| retail       | `HISTORICAL`, `PREDICTIVE` |
| brand        | `HISTORICAL`, `PREDICTIVE`, `LAPSED_BUYERS` |
| persona      | `LIFESTYLE`, `LIFESTAGE`, `AUTO`, `SHOPPING_HABITS`, `FOOD_BEVERAGES` |
| demographic  | `AGE`, `GENDER`, `HOUSEHOLD_INCOME` |
| custom       | `RULE_BASED`, `PROPENSITY`, `BRAND_AFFINITY`, `LOOKALIKE`, `ADVANCED`, `EXTERNAL` |

Response:
- `totalResults` (integer)
- `contextual` (array) — objects with `id`, `name`, `taxonPath`, `reach` (TIER_1–TIER_7), `isDisabled`
- `behavioral` (array) — objects with `id`, `name`, `taxonPath`, `audienceType`, `attribute`, `isDisabled`

Reach tier mapping: LOW = TIER_1/2, MID = TIER_3/4, HIGH = TIER_5/6/7.

## Geo location targeting

Reference:
- https://developer.walmart.com/advertising-partners/docs/list-geo-location-targeting-in-a-campaign

### List geo locations

```
POST /api/v1/geoLocations/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[id]` (array, optional) — specific geo target IDs
- `searchText` (string, optional) — search query
- `startIndex` (integer, optional) — pagination offset
- `count` (integer, optional) — number of results

Response:
- `totalResults` (integer)
- `geoTargets` (array) — objects with `id`, `name`, `locationType` (`STATE`/`CITY`/`DMA`/`COUNTRY`), `parentId`, `parentName`, `parentType`, `countryCode`
