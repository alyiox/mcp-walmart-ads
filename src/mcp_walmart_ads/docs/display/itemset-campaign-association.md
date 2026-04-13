# Itemset Campaign Association API (Display)

Reference:
- https://developer.walmart.com/advertising-partners/docs/add-itemsets-to-campaigns
- https://developer.walmart.com/advertising-partners/docs/list-itemset-campaign-association-copy

Associates itemsets with campaigns for measurement (featured/halo). Required for SKU-level reporting.

## Add itemset to campaign

```
POST /api/v1/itemsetAssociation
```

Body:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `itemsetId` (integer, conditional) — featured itemset ID (must be `BUILT`); omit to remove
- `itemsetType` (string, optional) — `"featured"`
- `haloAssociationType` (string, optional) — `NONE` (default) | `BRAND` | `CATEGORY` | `CUSTOM`
- `haloItemsetId` (integer, conditional) — required when `haloAssociationType=CUSTOM`

Response:
- `code` (string) — `success` or `failure`
- `campaignId` (integer)
- `itemsetId` (integer)
- `details` (array)

Behavior:
- Omitting `itemsetId` removes the featured itemset and any auto-created halo itemsets.
- CUSTOM halo itemsets persist when the featured itemset is removed.
- Halo association is available only for campaigns with start dates on or after 04/01/2025.

## List itemset campaign associations

```
POST /api/v1/itemsetAssociation/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[campaignId]` (array, optional)
- `startIndex` (integer, optional)
- `count` (integer, optional)

Response:
- `totalResults` (integer)
- `associations` (array) — objects with `campaignId`, `itemsetId`, `itemsetType`, `haloAssociationType`, `haloItemsetId`

## Notes

- A campaign can have one featured itemset and one halo itemset.
- Featured itemsets must be in `BUILT` status before associating.
- Halo itemsets are auto-generated based on the featured itemset unless `CUSTOM` is specified.
