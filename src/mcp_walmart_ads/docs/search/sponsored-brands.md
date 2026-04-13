# Sponsored Brands API (Sponsored Search)

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/overview-5
- https://developer.walmart.com/advertising-partners-search/docs/overview-7
- https://developer.walmart.com/advertising-partners-search/docs/sponsored-brands-workflows

Sponsored Brands Ads (SBA) require a profile and a review before a campaign can go live.

## Profile

### Create SBA profile

```
POST /api/v1/sbaProfile?advertiserId={advertiserId}
```

Body:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `brandName` (string, required)
- `brandLogoUrl` (string, optional) — URL of uploaded logo image
- `customImageUrl` (string, optional) — URL of uploaded custom image
- `headlineText` (string, required) — ad headline, max 45 chars
- `clickUrl` (string, required) — destination URL

### List SBA profiles

```
GET /api/v1/sbaProfile
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)

### Update SBA profile

```
PUT /api/v1/sbaProfile?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `sbaProfileId` plus fields to update.

### Upload logo image

```
POST /api/v1/sbaProfile/image?advertiserId={advertiserId}
```

Body: multipart/form-data with the image file.

Response: `{ "imageUrl": "..." }` — use the URL in the profile's `brandLogoUrl`.

### Upload custom image

```
POST /api/v1/sbaProfile/customImage?advertiserId={advertiserId}
```

Body: multipart/form-data with the image file.

Response: `{ "imageId": "...", "imageUrl": "..." }`

### Delete custom image

```
DELETE /api/v1/sbaProfile/customImage/{imageId}?advertiserId={advertiserId}
```

## Review

SBA campaigns must pass review before going live.

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/submit-campaign-review
- https://developer.walmart.com/advertising-partners-search/docs/fetch-review-status
- https://developer.walmart.com/advertising-partners-search/docs/cancel-sponsored-brands-campaign-review

### Submit campaign for review

```
POST /api/v1/sbaReview?advertiserId={advertiserId}
```

Body:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)

### Fetch review status

```
GET /api/v1/sbaReview
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)

Response fields: `campaignId`, `reviewStatus` (`pending` | `approved` | `rejected`), `reviewComments`.

### Cancel review

```
DELETE /api/v1/sbaReview?advertiserId={advertiserId}&campaignId={campaignId}
```

## Notes

- Only one ad group is allowed per SBA campaign.
- Campaign cannot go live without an approved review.
- See workflow guide: https://developer.walmart.com/advertising-partners-search/docs/setting-up-a-sponsored-brands-campaign
