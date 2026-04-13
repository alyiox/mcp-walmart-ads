# Sponsored Videos API (Sponsored Search)

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/overview-8
- https://developer.walmart.com/advertising-partners-search/docs/overview-9
- https://developer.walmart.com/advertising-partners-search/docs/what-is-sponsored-videos
- https://developer.walmart.com/advertising-partners-search/docs/sponsored-videos-workflows

Sponsored Videos (SV) campaigns require video media upload, ad group media association, and a review before going live.

## Media Upload (3-step)

### Step 1 — Initiate upload

```
POST /api/v1/media?advertiserId={advertiserId}
```

Body:
- `advertiserId` (integer, required)
- `mediaName` (string, required)
- `mediaType` (string, required) — `video`
- `fileName` (string, required) — original file name

Response: `{ "mediaId": "...", "uploadLocation": "..." }`

### Step 2 — Upload file to upload location

```
PUT {uploadLocation}
```

PUT the raw video file bytes to the pre-signed `uploadLocation` URL returned in Step 1.

### Step 3 — Complete upload

```
POST /api/v1/media/complete?advertiserId={advertiserId}
```

Body:
- `advertiserId` (integer, required)
- `mediaId` (string, required)

## Media Management

### Update media details

```
PUT /api/v1/media?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `mediaId` plus fields to update (`mediaName`, `status`).

### List all media

```
GET /api/v1/media
```

Query params:
- `advertiserId` (integer, required)

### Update closed caption

```
PUT /api/v1/media/closedCaption?advertiserId={advertiserId}
```

Body:
- `advertiserId` (integer, required)
- `mediaId` (string, required)
- `closedCaptionFile` (string) — URL or content of closed caption

### Delete media file

```
DELETE /api/v1/media/{mediaId}?advertiserId={advertiserId}
```

## Ad Group Media

Associates uploaded video media with an ad group.

Reference: https://developer.walmart.com/advertising-partners-search/docs/overview-9

### Create ad group media

```
POST /api/v1/adGroupMedia?advertiserId={advertiserId}
```

Body: JSON array.

Fields:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)
- `adGroupId` (integer, required)
- `mediaId` (string, required)
- `status` (string) — `enabled` | `disabled`

### List ad group media

```
GET /api/v1/adGroupMedia
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)
- `adGroupId` (integer, optional)

### Update ad group media

```
PUT /api/v1/adGroupMedia?advertiserId={advertiserId}
```

Body: JSON array. Each object must include `adGroupMediaId` plus fields to update.

## Review

Sponsored Video campaigns must pass review before going live.

Reference:
- https://developer.walmart.com/advertising-partners-search/docs/submit-campaign-review-copy
- https://developer.walmart.com/advertising-partners-search/docs/fetch-review-status-copy
- https://developer.walmart.com/advertising-partners-search/docs/cancel-sponsored-brands-campaign-review-copy

### Submit campaign for review

```
POST /api/v1/videoReview?advertiserId={advertiserId}
```

Body:
- `advertiserId` (integer, required)
- `campaignId` (integer, required)

### Fetch review status

```
GET /api/v1/videoReview
```

Query params:
- `advertiserId` (integer, required)
- `campaignId` (integer, optional)

Response fields: `campaignId`, `reviewStatus` (`pending` | `approved` | `rejected`), `reviewComments`.

### Cancel review

```
DELETE /api/v1/videoReview?advertiserId={advertiserId}&campaignId={campaignId}
```

## Notes

- Video format requirements: MP4 or MOV, max 500 MB, 15–30 seconds.
- Campaign cannot go live without an approved review.
- See workflow guide: https://developer.walmart.com/advertising-partners-search/docs/setting-up-a-sponsored-videos-campaign
