# Video API (Display)

Reference: https://developer.walmart.com/advertising-partners/docs/upload-video

Upload and manage video assets for Display ad creatives.

## Upload video asset

```
POST /api/v1/assets/video
```

Body: multipart/form-data
- `advertiserId` (integer, required)
- `videoFile` (file, required) — mp4 or mov, max 500 MB
- `profileName` (string, required) — fixed value `checkin`
- `generateCaptions` (boolean, required) — `true` to auto-generate captions

Video requirements:
- Format: mp4 or mov
- Max size: 500 MB
- Resolution: 1280×720 to 3840×2160 px, 16:9 aspect ratio
- Duration: 5–45 seconds

Response:
- `code` (string) — `success` or `failure`
- `assetId` (string) — video asset UUID; use in creative `adUnits[].images`
- `captioningJobId` (string) — caption job ID (when `generateCaptions=true`)

## Get video transcription status

```
GET /api/v1/assets/video/captions/status?advertiserId={advertiserId}&captioningJobId={captioningJobId}
```

Response:
- `jobStatus` (string) — `pending` | `processing` | `done` | `failed`
- `assetId` (string)

## Upload closed caption file

```
POST /api/v1/assets/video/captions
```

Body: multipart/form-data
- `advertiserId` (integer, required)
- `assetId` (string, required) — video asset to attach captions to
- `captionFile` (file, required) — VTT or SRT format

Response: `{ "code": "success", "captionAssetId": "uuid" }`

## Get latest caption file

```
GET /api/v1/assets/video/captions?advertiserId={advertiserId}&assetId={assetId}
```

Response:
- `captionAssetId` (string)
- `captionFileUrl` (string) — download URL for the caption file
- `status` (string) — `APPROVED` | `PENDING` | `REJECTED`

## Notes

- `assetId` from the upload response is referenced in creative `adUnits` to associate the video with a creative.
- Caption generation via `generateCaptions=true` is asynchronous; poll transcription status before submitting the creative.
- Manual caption upload overrides auto-generated captions.
