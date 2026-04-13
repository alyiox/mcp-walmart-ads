# Creative API (Display)

Reference:
- https://developer.walmart.com/advertising-partners/docs/overview-1
- https://developer.walmart.com/advertising-partners/docs/creative-v2

> **Migration note:** Migrate from Creative v1 to Creative v2 by April 30, 2026.

## Creative v1

### Upload creative image

```
POST /api/v1/assets/image
```

Body: multipart/form-data
- `advertiserId` (integer, required)
- `imageFile` (file, required)

Response: `{ "code": "success", "assetId": "uuid" }`

Use `assetId` in the `adUnits[].images` array when creating a creative.

### Create creative

```
POST /api/v1/creatives
```

Body:
- `advertiserId` (integer, required)
- `metadata` (object, required):
  - `name` (string, required, max 255 chars)
  - `templateId` (integer, required) — fixed value `436`
  - `folderId` (UUID, optional) — defaults to home folder if null
  - `subscribeEnabled` (boolean, optional)
  - `associatedItems` (array, conditional) — required when `subscribeEnabled=true`; single item ID
- `adUnits` (object, required) — keyed by ad unit name:
  - Supported units: `marqueeDesktop`, `marqueeApp`, `skylineDesktop`, `skylineApp`, `skylineDesktopV2`, `skylineAppV2`, `skylineDesktopV3`, `skylineAppV3`, `brandboxDesktop`, `brandboxApp`, `galleryDesktop`, `galleryApp`, `tileDesktop`, `tileApp`
  - Each unit contains:
    - `headline` (string, required) — 25–35 chars depending on unit
    - `subhead` (string, optional) — must end with `.!?*`
    - `cta` (string, required) — call-to-action; sentence case
    - `logoAltText` (string, optional, max 150 chars)
    - `imageAltText` (string, optional, max 150 chars)
    - `images` (array) — desktop/mobile image and logo assets with `assetId`
    - `backgroundColorHex` (string, optional) — Skyline v3 units only
    - `textColor` (string, optional) — `gray` or `white`; Skyline v3 units only
    - `legalDisclaimerText` (string, optional, max 600 chars)
    - `legalDisclaimerLabel` / `legalDisclaimerPopUpCopy` (strings, optional)
    - `variantId` (string) — fixed value `436`

Response: `{ "code": "success", "creativeId": "uuid" }`

### List creatives

```
POST /api/v1/creatives/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[creativeId]` (array, optional)
- `Filter[status]` (string, optional) — `DRAFT` | `PENDING_APPROVAL` | `APPROVED` | `REJECTED`
- `Filter[folderId]` (string, optional)
- `startIndex` (integer, optional)
- `count` (integer, optional)

Response: `{ "totalResults": N, "creatives": [...] }`

### Get creative metadata

```
GET /api/v1/creatives/{creativeId}?advertiserId={advertiserId}
```

Returns full creative object with all fields and current status.

### Request creative preview

```
POST /api/v1/creativePreview
```

Body: `{ "advertiserId": N, "creativeId": "uuid" }`

Response: `{ "code": "success", "previewJobId": "uuid" }`

### Get preview status

```
GET /api/v1/creativePreview?advertiserId={advertiserId}&previewJobId={previewJobId}
```

Response: `{ "jobStatus": "pending"|"done"|"failed", "previewImages": [...] }`

### Submit creative for moderation

```
POST /api/v1/creativeSubmission
```

Body: `{ "advertiserId": N, "creativeId": "uuid" }`

Response: `{ "code": "success", "submissionId": "uuid" }`

### Get submission status

```
GET /api/v1/creativeSubmission?advertiserId={advertiserId}&creativeId={creativeId}
```

Response: `{ "reviewStatus": "PENDING_APPROVAL"|"APPROVED"|"REJECTED", "reviewComments": [...] }`

### Update creative (full replace)

```
PUT /api/v1/creatives
```

Body: same structure as create, with `creativeId` included. Replaces all fields.

### Update creative (partial)

```
PATCH /api/v1/creatives
```

Body: `{ "advertiserId": N, "creativeId": "uuid", ...fields to update }`

### Resolve moderation comments

```
POST /api/v1/creatives/resolveComments
```

Body: `{ "advertiserId": N, "creativeId": "uuid", "commentIds": ["..."] }`

### Clone creative

```
POST /api/v1/creatives/clone
```

Body: `{ "advertiserId": N, "creativeId": "uuid", "name": "clone name" }`

Response: `{ "code": "success", "creativeId": "new-uuid" }`

### Move creative to folder

```
PUT /api/v1/creatives/move
```

Body: `{ "advertiserId": N, "creativeId": "uuid", "folderId": "uuid" }`

### Delete creative

```
DELETE /api/v1/creatives?advertiserId={advertiserId}&creativeId={creativeId}
```

### Restore creative

```
PUT /api/v1/creatives/restore
```

Body: `{ "advertiserId": N, "creativeId": "uuid" }`

### Moderation Assist

AI-assisted moderation feedback before submission.

#### Initiate moderation assist

```
POST /api/v1/creatives/moderation-assist
```

Body: `{ "advertiserId": N, "creativeId": "uuid" }`

Response: `{ "jobId": "uuid" }`

#### Get moderation assist results

```
GET /api/v1/creatives/moderation-assist?advertiserId={advertiserId}&jobId={jobId}
```

#### Get moderation comments

```
GET /api/v1/creatives/moderation-comments?advertiserId={advertiserId}&creativeId={creativeId}
```

#### Submit substantiation, acknowledgment, or appeal

```
POST /api/v1/creatives/moderation-response
```

Body: `{ "advertiserId": N, "creativeId": "uuid", "responseType": "SUBSTANTIATION"|"ACKNOWLEDGMENT"|"APPEAL", "message": "..." }`

### Skyline v3 background color recommendations

```
POST /api/v1/creatives/background-color-recommendations
```

Body: `{ "advertiserId": N, "assetId": "uuid" }`

Response: `{ "recommendations": [{ "hex": "#xxxxxx", "score": N }] }`

---

## Creative v2

Reference: https://developer.walmart.com/advertising-partners/docs/creative-v2

### Create creative v2

```
POST /api/v2/creatives
```

Simplified body structure with updated field names and support for new ad unit types.

Body:
- `advertiserId` (integer, required)
- `metadata` (object) — same as v1 but with `templateId` determined by ad unit type
- `adUnits` (object) — same ad unit keys as v1 with updated field schema

Response: `{ "code": "success", "creativeId": "uuid" }`

### Get creative metadata v2

```
GET /api/v2/creatives/{creativeId}?advertiserId={advertiserId}
```

### Update creative v2 (full replace)

```
PUT /api/v2/creatives
```

### Update creative v2 (partial)

```
PATCH /api/v2/creatives
```

## Notes

- Creatives must be `APPROVED` or `PENDING_APPROVAL` to associate with ad groups.
- `templateId` for v1 is always `436`.
- v2 is required for new ad unit types introduced after the v1 deprecation deadline.
