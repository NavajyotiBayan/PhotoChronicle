# PhotoChronicle

**Preserve Your Timeline**

PhotoChronicle is a local Windows browser application for restoring and organizing media exported with Google Takeout. It reads Google metadata JSON sidecars, resolves the best available timestamp, organizes media into date folders, restores Windows filesystem dates, and can optionally write the corrected date into media metadata with the bundled ExifTool.

##  How to Use PhotoChronicle

1. 📦 **Download & extract** the PhotoChronicle ZIP.
2. 📂 Open the extracted **PhotoChronicle** folder.
3. ▶️ Double-click **`start.bat`**.
4. 🌐 PhotoChronicle will start its **local service** and automatically open in your browser.
5. 💻 Keep the terminal window open while PhotoChronicle is running.

> 🔒 **Privacy first**
> PhotoChronicle is **local-first by design**. Your photos, videos, and metadata are processed on your own computer through the local PhotoChronicle service — **nothing is uploaded to a cloud server.**

**Your memories stay on your machine.**
**Your timeline. Your archive. Your control.**


## Highlights

- 100% local processing: the application binds to `127.0.0.1` and does not upload media to an online service.
- Browser-based UI with a native Windows output-folder picker.
- Google Takeout JSON sidecar matching with multiple naming conventions.
- Timestamp priority: `photoTakenTime` → `creationTime` → `modificationTime` → `dateTaken` → `dateTimeOriginal` → `createDate` → common fallback fields.
- Handles Unix seconds, Unix milliseconds, ISO-8601 strings, and common camera date formats.
- Recursive metadata lookup for lightly wrapped JSON structures.
- Date layouts: `YYYY/MM/DD`, `YYYY/MM`, `YYYY`, and `YYYY-MM-DD`.
- Duplicate policies: rename safely, skip, or overwrite.
- Missing JSON is placed in `NO JSON FILES`.
- JSON without a usable timestamp is placed in `NO TIMESTAMP` instead of guessing a date.
- Same-stem Live Photo / motion-photo pairs are kept together and receive the same resolved timestamp.
- Windows Created / Modified / Accessed timestamps are restored from the resolved Takeout timestamp.
- Optional EXIF / QuickTime metadata writing through the bundled ExifTool.
- Live processing console, cancellation, session log, and completion summary.
- Five low-glare Eye Comfort themes.
- Temporary upload/staging data is removed after processing.
- The source archive selected in the browser is never directly modified. `Move staged copy` only moves the local staging copy created by PhotoChronicle.

## Media compatibility

PhotoChronicle recognizes a broad set of common photo, RAW, image-sequence, and video formats so Google Takeout archives are not limited to web-friendly files.

### Images / photos

JPG, JPEG, JPE, JFIF, JFI, JIF, PNG, GIF, WebP, AVIF, JXL, QOI, HEIC, HEIF, HEICS, HEIFS, TIFF, TIF, BMP, ICO, JPEG 2000 (JP2/J2K/JPF/JPX/JPM), DNG, RAW, ARW, SRF, SR2, CRW, CR2, CR3, NEF, NRW, ORF, RW2, RAF, PEF, PTX, SRW, DCR, K25, KDC, ERF, FFF, MOS, MEF, MRW, 3FR, IIQ, RWL, X3F, GPR, CAP, BAY, PSD, PSB, EPS, MPO, and JPS.

### Video

MP4, M4V, MOV, QT, AVI, MKV, WebM, 3GP, 3G2, MTS, M2TS, TS, M2V, MPG, MPEG, VOB, WMV, ASF, FLV, F4V, OGV, MXF, and DV.

ExifTool determines what metadata a particular media format can actually accept. PhotoChronicle reports metadata-write failures without treating them as a failed file copy.

## JSON compatibility

PhotoChronicle first checks the sidecar next to the media file, then uses a tolerant filename index for common Takeout naming variations, including:

- `IMG_0001.JPG.json`
- `IMG_0001.JPG.supplemental-metadata.json`
- `IMG_0001.JPG.metadata.json`
- `IMG_0001.json`
- `IMG_0001.supplemental-metadata.json`
- `IMG_0001.metadata.json`

The parser accepts Google-style objects such as `{ "timestamp": "..." }`, plain numeric timestamp values, Unix seconds, Unix milliseconds, ISO-8601 timestamps, and common camera date strings.

If metadata is missing or unusable, PhotoChronicle **does not invent a date**.

## Workflow

1. Choose or drag a Google Takeout folder.
2. Let PhotoChronicle scan the folder and show detected media formats.
3. Choose the real Windows output folder.
4. Select the date-folder and duplicate rules.
5. Choose whether to write media metadata.
6. Review the operation.
7. Start processing.
8. Open the completed output folder from the success dialog.

## Browser compatibility

Folder selection uses the widely implemented `webkitdirectory` directory-upload interface. Current Firefox, Edge, and Chromium-based browsers support directory selection; recent Firefox versions support the relevant directory APIs. For the most predictable Windows experience, use current Firefox, Microsoft Edge, or Google Chrome.

## Requirements

- Windows 10/11
- Python 3.10 or newer
- A modern browser
- Internet access only for the first dependency installation if Flask is not already available in the local virtual environment

ExifTool is bundled in `tools/exiftool(-k).exe`.

## Run

Double-click:

```text
start.bat
```

The launcher creates a local `.venv`, installs the single Python dependency, starts the local service, waits for `127.0.0.1:8765` to respond, and then opens the browser.

## Repository layout

```text
PhotoChronicle/
├── app.py
├── start.bat
├── requirements.txt
├── LICENSE
├── VERSION.txt
├── README.md
├── tools/
│   └── exiftool(-k).exe
├── static/
│   ├── app.css
│   └── app.js
└── templates/
    └── index.html
```

Runtime-only folders are intentionally ignored by Git:

```text
work/
outputs/
.venv/
__pycache__/
```

## Privacy

PhotoChronicle is designed as a local utility. The Flask service listens only on `127.0.0.1`. Selected files are staged locally so the browser can hand them to the local Python process; they are not sent to PhotoChronicle's developer or to a remote server.

## Third-party component

PhotoChronicle bundles ExifTool by Phil Harvey for local metadata writing. See `THIRD-PARTY-NOTICES.md` for attribution and licensing information.

## License

MIT License for PhotoChronicle source code. See `LICENSE`.

## Version

**1.0.0 — Stable local release**
