# Folder API (Display)

Reference: https://developer.walmart.com/advertising-partners/docs/list-all-the-folders

Folders organize creatives within an advertiser account.

## List folders

```
POST /api/v1/folders/list
```

Body:
- `advertiserId` (integer, required)
- `Filter[folderId]` (string, optional) — fetch subfolders of this folder
- `Filter[search]` (string, optional) — search by folder ID, name, or user
- `startIndex` (integer, optional)
- `count` (integer, optional)

Response:
- `totalResults` (integer)
- `response` (array):
  - `folderId` (string)
  - `parentFolderId` (string)
  - `advertiserId` (integer)
  - `type` (string) — `FOLDER`
  - `name` (string)
  - `creationDate` (string)
  - `lastUpdatedDate` (string)

## Create folder

```
POST /api/v1/folders
```

Body:
- `advertiserId` (integer, required)
- `name` (string, required)
- `parentFolderId` (string, optional) — omit to create at root

Response: `{ "code": "success", "folderId": "uuid" }`

## Clone folder

```
POST /api/v1/folders/clone
```

Body:
- `advertiserId` (integer, required)
- `folderId` (string, required)
- `name` (string, required) — name for the cloned folder

Response: `{ "code": "success", "folderId": "new-uuid" }`

## Update folder

```
PUT /api/v1/folders
```

Body:
- `advertiserId` (integer, required)
- `folderId` (string, required)
- `name` (string, optional)

## Move folder

```
PUT /api/v1/folders/move
```

Body:
- `advertiserId` (integer, required)
- `folderId` (string, required)
- `targetFolderId` (string, required) — destination parent folder

## Restore folder

```
PUT /api/v1/folders/restore
```

Body:
- `advertiserId` (integer, required)
- `folderId` (string, required)

## Delete folder

```
DELETE /api/v1/folders
```

Body:
- `advertiserId` (integer, required)
- `folderId` (string, required)

## Notes

- Deleting a folder moves its contents to the recycle bin; use restore to recover.
- A creative's `folderId` (in its metadata) determines where it appears.
- Root folder is the default when `folderId` is null during creative creation.
