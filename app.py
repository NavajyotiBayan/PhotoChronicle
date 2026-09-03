from flask import Flask, render_template, request, jsonify
from pathlib import Path
from datetime import datetime, timezone
import shutil
import json
import threading
import uuid
import subprocess
import os
import time
import re

APP_VERSION = "1.0.0"
BASE = Path(__file__).resolve().parent
WORK = BASE / "work"
OUTPUTS = BASE / "outputs"
WORK.mkdir(exist_ok=True)
OUTPUTS.mkdir(exist_ok=True)
EXIF = BASE / "tools" / "exiftool(-k).exe"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024 * 1024  # 16 GB upload ceiling

jobs = {}
scans = {}

# Google Photos / common camera image formats. Google Takeout itself can contain
# original camera formats, so this list intentionally goes beyond web-only images.
PHOTO_EXT = {
    ".jpg", ".jpeg", ".jpe", ".jfif", ".jfi", ".jif",
    ".png", ".gif", ".webp", ".avif", ".jxl", ".qoi",
    ".heic", ".heif", ".heics", ".heifs",
    ".tif", ".tiff", ".bmp", ".ico",
    ".jp2", ".j2k", ".jpf", ".jpx", ".jpm",
    ".dng", ".raw", ".arw", ".srf", ".sr2", ".crw", ".cr2", ".cr3",
    ".nef", ".nrw", ".orf", ".rw2", ".raf", ".pef", ".ptx", ".srw",
    ".dcr", ".k25", ".kdc", ".erf", ".fff", ".mos", ".mef", ".mrw",
    ".3fr", ".iiq", ".rwl", ".x3f", ".gpr", ".cap", ".bay",
    ".psd", ".psb", ".eps", ".mpo", ".jps",
}

VIDEO_EXT = {
    ".mp4", ".m4v", ".mov", ".qt", ".avi", ".mkv", ".webm",
    ".3gp", ".3g2", ".mts", ".m2ts", ".ts", ".m2v", ".mpg", ".mpeg",
    ".vob", ".wmv", ".asf", ".flv", ".f4v", ".ogv", ".mxf", ".dv",
}

MEDIA_EXT = PHOTO_EXT | VIDEO_EXT

# Common Google/Takeout metadata fields, ordered from most authoritative to least.
TIMESTAMP_FIELDS = (
    "photoTakenTime",
    "creationTime",
    "modificationTime",
    "dateTaken",
    "dateTimeOriginal",
    "createDate",
    "dateTime",
    "timestamp",
)


def safe_rel(name):
    """Normalize a browser-provided relative path and prevent traversal."""
    name = str(name or "").replace("\\", "/")
    p = Path(name.lstrip("/"))
    parts = [x for x in p.parts if x not in ("", ".", "..")]
    return Path(*parts) if parts else Path("unnamed")


def normalize_key(value):
    """Normalize filenames for tolerant JSON sidecar matching."""
    s = str(value or "").replace("\\", "/").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def stem_variants(media):
    """Return progressively broader keys used to match Google sidecars."""
    rel = normalize_key(media)
    name = Path(rel).name
    stem = Path(name).stem
    variants = {
        rel,
        name,
        name + ".json",
        name + ".supplemental-metadata.json",
        name + ".metadata.json",
        stem + ".json",
        stem + ".supplemental-metadata.json",
        stem + ".metadata.json",
        stem,
    }
    # Google/OS duplicate suffixes can cause small naming differences.
    base = re.sub(r"\s*\(\d+\)$", "", stem)
    if base != stem:
        variants.update({base, base + ".json", base + ".supplemental-metadata.json", base + ".metadata.json"})
    return variants


def parse_timestamp(value):
    """Parse Unix seconds/milliseconds or common ISO/date strings."""
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        for key in ("timestamp", "value", "date", "datetime", "dateTime"):
            if key in value:
                result = parse_timestamp(value[key])
                if result:
                    return result
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        if n == 0:
            return None
        if abs(n) > 100_000_000_000:  # milliseconds
            n /= 1000.0
        try:
            return datetime.fromtimestamp(n, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text or text == "0":
        return None
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return parse_timestamp(float(text))
    candidates = [text, text.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            pass
    for fmt in (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _find_timestamp_in_object(obj, depth=0):
    """Tolerantly inspect nested metadata without walking arbitrary huge trees forever."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for field in TIMESTAMP_FIELDS:
            if field in obj:
                dt = parse_timestamp(obj[field])
                if dt:
                    return dt
        # Google sometimes nests metadata below small wrapper objects.
        for value in obj.values():
            if isinstance(value, (dict, list)):
                dt = _find_timestamp_in_object(value, depth + 1)
                if dt:
                    return dt
    elif isinstance(obj, list):
        for value in obj[:50]:
            dt = _find_timestamp_in_object(value, depth + 1)
            if dt:
                return dt
    return None


def json_timestamp(path):
    try:
        # utf-8-sig handles Google JSON with or without a BOM.
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:
        return None
    return _find_timestamp_in_object(data)


def build_json_index(root):
    """Index JSON sidecars once; ambiguous global filename matches are discarded."""
    index = {}
    json_files = []
    for p in root.rglob("*.json"):
        json_files.append(p)
        rel = p.relative_to(root)
        rel_key = normalize_key(rel)
        name_key = normalize_key(p.name)
        stem_key = normalize_key(p.stem)
        keys = {
            rel_key, name_key, stem_key,
            name_key.replace(".supplemental-metadata.json", ""),
            name_key.replace(".metadata.json", ""),
            name_key.replace(".json", ""),
        }
        # Also index parent-relative names, useful when Takeout has nested albums.
        for key in list(keys):
            if key:
                index.setdefault(key, []).append(p)
    return index, json_files


def find_json(root, media, index=None):
    """Match the closest sensible sidecar before falling back to a global filename index."""
    candidates = [
        media.with_name(media.name + ".json"),
        media.with_name(media.name + ".supplemental-metadata.json"),
        media.with_name(media.name + ".metadata.json"),
        media.with_suffix(".json"),
        media.with_name(media.stem + ".supplemental-metadata.json"),
        media.with_name(media.stem + ".metadata.json"),
    ]
    for p in candidates:
        if p.exists():
            return p
    if index is None:
        return None
    for key in stem_variants(media):
        matches = index.get(normalize_key(key), [])
        if len(matches) == 1 and matches[0].exists():
            return matches[0]
    return None


def unique_dest(folder, name, mode):
    dest = folder / name
    if not dest.exists() or mode == "overwrite":
        return dest
    if mode == "skip":
        return None
    stem, ext = Path(name).stem, Path(name).suffix
    i = 1
    while dest.exists():
        dest = folder / f"{stem} ({i}){ext}"
        i += 1
    return dest


def log(job, level, message):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "message": message}
    job.setdefault("logs", []).append(entry)
    if len(job["logs"]) > 1500:
        job["logs"] = job["logs"][-1500:]


def set_file_times(path, ts):
    """Set Created/Modified/Accessed to the resolved Takeout timestamp on Windows."""
    epoch = ts.replace(tzinfo=timezone.utc).timestamp()
    os.utime(path, (epoch, epoch))
    if os.name != "nt":
        return True, "mtime/atime updated"
    try:
        import ctypes
        from ctypes import wintypes
        FILE_WRITE_ATTRIBUTES = 0x0100
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        handle = ctypes.windll.kernel32.CreateFileW(
            str(path), FILE_WRITE_ATTRIBUTES, 0, None, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL, None
        )
        if handle in (0, INVALID_HANDLE_VALUE):
            return False, "Could not open file attributes"

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        ft_value = int(epoch * 10_000_000) + 116444736000000000
        ft = FILETIME(ft_value & 0xFFFFFFFF, (ft_value >> 32) & 0xFFFFFFFF)
        ok = ctypes.windll.kernel32.SetFileTime(
            handle, ctypes.byref(ft), ctypes.byref(ft), ctypes.byref(ft)
        )
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok), "Windows Created/Modified/Accessed times updated" if ok else "SetFileTime failed"
    except Exception as exc:
        return False, str(exc)


def exif_write(path, ts):
    if not EXIF.exists():
        return False, "ExifTool not found"
    stamp = ts.strftime("%Y:%m:%d %H:%M:%S")
    if path.suffix.lower() in PHOTO_EXT:
        args = [
            "-overwrite_original",
            f"-DateTimeOriginal={stamp}",
            f"-CreateDate={stamp}",
            f"-ModifyDate={stamp}",
            f"-AllDates={stamp}",
            str(path),
        ]
    else:
        args = ["-overwrite_original", f"-CreateDate={stamp}", f"-ModifyDate={stamp}", str(path)]
    try:
        r = subprocess.run(
            [str(EXIF), *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            text=True, timeout=120
        )
        return r.returncode == 0, r.stdout.strip()[-700:]
    except Exception as exc:
        return False, str(exc)


def structure_path(ts, structure):
    if structure == "YYYY/MM":
        return Path(f"{ts:%Y}/{ts:%m}")
    if structure == "YYYY":
        return Path(f"{ts:%Y}")
    if structure == "YYYY-MM-DD":
        return Path(f"{ts:%Y-%m-%d}")
    return Path(f"{ts:%Y}/{ts:%m}/{ts:%d}")


def copy_media(src, dest, mode):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if mode == "Move":
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)


def process_one(src, dest, ts, options, j, stats):
    copy_media(src, dest, options.get("copyMode", "Copy"))
    stats["fixed"] += 1
    log(j, "OK", f"{ts:%Y-%m-%d %H:%M:%S} → {dest.relative_to(Path(options['outputPath']))}")
    if options.get("writeMeta", True) and options.get("useExif", True):
        j.update(operation="Writing media metadata")
        ok, detail = exif_write(dest, ts)
        if ok:
            stats["exif_written"] += 1
            log(j, "META", f"Media metadata updated: {dest.name}")
        else:
            stats["metadata_errors"] += 1
            log(j, "WARN", f"Metadata write failed: {dest.name} — {detail}")
    j.update(operation="Restoring filesystem date")
    ok, detail = set_file_times(dest, ts)
    if ok:
        stats["filesystem_dates"] += 1
        log(j, "DATE", f"Filesystem date fixed: {ts:%Y-%m-%d %H:%M:%S} → {dest.name}")
    else:
        stats["filesystem_date_errors"] += 1
        log(j, "WARN", f"Filesystem date update failed: {dest.name} — {detail}")


def media_group_key(path):
    # Keep same-directory, same-stem photo/video pairs together.
    stem = re.sub(r"\s*\(\d+\)$", "", path.stem).strip().lower()
    return (str(path.parent).lower(), stem)


def build_media_groups(media):
    groups = {}
    for p in media:
        groups.setdefault(media_group_key(p), []).append(p)
    return list(groups.values())


def process_job(job_id, files, options):
    j = jobs[job_id]
    root = WORK / job_id
    out = Path(options.get("outputPath") or (OUTPUTS / job_id)).expanduser().resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)
        media = []
        for f in files:
            rel = safe_rel(f.get("relative", ""))
            src = root / rel
            src.parent.mkdir(parents=True, exist_ok=True)
            Path(f["path"]).replace(src)
            if src.suffix.lower() in MEDIA_EXT:
                media.append(src)

        json_index, json_files = build_json_index(root)
        total = len(media)
        stats = {
            "total": total, "fixed": 0, "no_json": 0, "no_timestamp": 0,
            "skipped": 0, "errors": 0, "live_pairs": 0,
            "exif_written": 0, "filesystem_dates": 0,
            "metadata_errors": 0, "filesystem_date_errors": 0,
            "json_files": len(json_files),
        }
        options["outputPath"] = str(out)
        j.update(status="processing", total=total, current=0, percent=0, file="",
                  operation="Indexing metadata", output_path=str(out), message="Preparing archive…")
        log(j, "INFO", f"PhotoChronicle {APP_VERSION} — scan complete: {total:,} media files found.")
        log(j, "INFO", f"JSON sidecars found: {len(json_files):,}")
        log(j, "INFO", f"Output folder: {out}")
        log(j, "INFO", f"Structure: {options.get('structure', 'YYYY/MM/DD')} | Duplicates: {options.get('duplicates', 'Rename')} | Mode: {options.get('copyMode', 'Copy')}")
        log(j, "INFO", "Timestamp policy: JSON metadata first; filesystem dates restored from resolved timestamp.")
        if options.get("writeMeta") and options.get("useExif"):
            log(j, "INFO", "Optional media metadata writing is enabled.")

        processed = set()
        groups = build_media_groups(media)
        group_total = sum(len(g) for g in groups)
        group_index = 0
        for group in groups:
            if j.get("cancel"):
                break
            group_index += 1
            # Resolve one timestamp for the whole same-stem group. This covers
            # Live Photos where only one side of the pair has a JSON sidecar.
            resolved = None
            resolved_json = None
            for member in group:
                jp = find_json(root, member, json_index)
                if jp:
                    candidate = json_timestamp(jp)
                    if candidate:
                        resolved, resolved_json = candidate, jp
                        break

            for member in group:
                if j.get("cancel"):
                    break
                if str(member) in processed:
                    continue
                idx_display = min(total, max(1, len(processed) + 1))
                j.update(current=idx_display, percent=int(idx_display * 100 / max(1, total)),
                         file=member.name, operation="Reading JSON sidecar", message=f"Processing {member.name}")

                jp = find_json(root, member, json_index)
                if not resolved:
                    if not jp:
                        stats["no_json"] += 1
                        destdir = out / "NO JSON FILES"
                        dest = unique_dest(destdir, member.name, options.get("duplicates", "Rename"))
                        if dest is None:
                            stats["skipped"] += 1
                            log(j, "WARN", f"SKIP duplicate without JSON: {member.name}")
                        else:
                            copy_media(member, dest, options.get("copyMode", "Copy"))
                            processed.add(str(member))
                            log(j, "WARN", f"NO JSON → {dest.relative_to(out)}")
                        continue
                    stats["no_timestamp"] += 1
                    destdir = out / "NO TIMESTAMP"
                    dest = unique_dest(destdir, member.name, options.get("duplicates", "Rename"))
                    if dest is None:
                        stats["skipped"] += 1
                        log(j, "WARN", f"SKIP duplicate without timestamp: {member.name} ({jp.name})")
                    else:
                        copy_media(member, dest, options.get("copyMode", "Copy"))
                        processed.add(str(member))
                        log(j, "WARN", f"NO TIMESTAMP → {dest.relative_to(out)} ({jp.name})")
                    continue

                destdir = out / structure_path(resolved, options.get("structure", "YYYY/MM/DD"))
                dest = unique_dest(destdir, member.name, options.get("duplicates", "Rename"))
                if dest is None:
                    stats["skipped"] += 1
                    log(j, "WARN", f"SKIP duplicate: {member.name}")
                    processed.add(str(member))
                    continue
                j.update(operation="Writing archive file")
                process_one(member, dest, resolved, options, j, stats)
                processed.add(str(member))
                if len(group) > 1:
                    stats["live_pairs"] += 1
                    log(j, "PAIR", f"Matched same-stem pair → {dest.relative_to(out)}")

        j.update(current=total, percent=100 if not j.get("cancel") else j.get("percent", 0))

        status = "cancelled" if j.get("cancel") else "complete"
        log(j, "OK" if status == "complete" else "WARN",
            f"Finished: {stats['fixed']:,} organized, {stats['no_json']:,} without JSON, {stats['no_timestamp']:,} without timestamp, {stats['skipped']:,} skipped.")
        # Write the final complete log, including the finishing entry.
        (out / "PhotoChronicle.log").write_text(
            "\n".join(f"[{x['time']}] {x['level']}: {x['message']}" for x in j.get("logs", [])),
            encoding="utf-8"
        )
        j.update(
            status=status,
            message="Processing cancelled" if status == "cancelled" else "Processing complete",
            stats=stats,
            percent=100 if status == "complete" else j.get("percent", 0),
            operation="Complete",
            output_path=str(out),
        )
    except Exception as exc:
        log(j, "ERROR", str(exc))
        j.update(status="error", message=str(exc), operation="Error")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        # Remove any scan/upload staging folders owned by this job after processing.
        for child in WORK.iterdir():
            if child.is_dir() and child.name.endswith("_scan") and not child.name.startswith(job_id):
                # Do not aggressively delete another active scan. Its lifecycle is handled below.
                pass


def start_job_from_manifest(manifest, opts):
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "status": "queued", "percent": 0, "current": 0, "total": 0,
        "file": "", "operation": "Queued", "message": "Preparing…", "logs": []
    }
    threading.Thread(target=process_job, args=(job_id, manifest, opts), daemon=True).start()
    return job_id


@app.get("/")
def index():
    return render_template("index.html", version=APP_VERSION)


@app.get("/health")
def health():
    return jsonify(status="online", service="PhotoChronicle", version=APP_VERSION, exiftool=EXIF.exists())


@app.post("/api/choose-output")
def choose_output():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Choose PhotoChronicle output folder")
        root.destroy()
        return jsonify(path=path or "")
    except Exception as exc:
        return jsonify(path="", error=str(exc)), 500


def save_uploads(file_list, staging):
    manifest = []
    for f in file_list:
        rel = safe_rel(f.filename)
        p = staging / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        f.save(p)
        manifest.append({"path": str(p), "relative": str(rel)})
    return manifest


@app.post("/api/scan")
def scan():
    files = request.files.getlist("files")
    if not files:
        return jsonify(error="No files selected"), 400
    sid = uuid.uuid4().hex[:10]
    staging = WORK / f"{sid}_scan"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        manifest = save_uploads(files, staging)
        media = 0; json_count = 0; ext_counts = {}
        for f in manifest:
            p = Path(f["path"])
            ext = p.suffix.lower()
            if ext in MEDIA_EXT:
                media += 1; ext_counts[ext] = ext_counts.get(ext, 0) + 1
            elif ext == ".json":
                json_count += 1
        scans[sid] = {"manifest": manifest, "media": media, "json": json_count, "files": len(files), "ext_counts": ext_counts, "staging": str(staging), "created": time.time()}
        return jsonify(scan_id=sid, media=media, json=json_count, files=len(files), extensions=ext_counts)
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        return jsonify(error=str(exc)), 500


@app.post("/api/start-scan-job")
def start_scan_job():
    data = request.get_json(force=True) or {}
    sid = data.get("scan_id")
    opts = data.get("options") or {}
    scan = scans.pop(sid, None)
    if not scan:
        return jsonify(error="Scan session expired. Please choose the folder again."), 400
    # Keep the staging manifest alive; process_job moves those files into its private job folder.
    job_id = start_job_from_manifest(scan["manifest"], opts)
    return jsonify(job_id=job_id)


@app.post("/api/process")
def process_upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify(error="No files selected"), 400
    staging = WORK / f"{uuid.uuid4().hex[:10]}_upload"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        manifest = save_uploads(files, staging)
        opts = json.loads(request.form.get("options", "{}"))
        return jsonify(job_id=start_job_from_manifest(manifest, opts))
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        return jsonify(error=str(exc)), 500


@app.get("/api/status/<job_id>")
def status(job_id):
    return jsonify(jobs.get(job_id, {"status": "missing"}))


@app.post("/api/cancel/<job_id>")
def cancel(job_id):
    if job_id in jobs:
        jobs[job_id]["cancel"] = True
        log(jobs[job_id], "WARN", "Cancellation requested by user.")
    return jsonify(ok=True)


@app.post("/api/open-output")
def open_output():
    data = request.get_json(force=True) or {}
    path = data.get("path", "")
    if not path:
        return jsonify(error="No output folder selected"), 400
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(p))
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return jsonify(ok=True)
    except Exception as exc:
        return jsonify(error=str(exc)), 500


@app.post("/api/cleanup-scan")
def cleanup_scan():
    data = request.get_json(force=True) or {}
    sid = data.get("scan_id")
    scan = scans.pop(sid, None)
    if scan:
        shutil.rmtree(scan.get("staging", ""), ignore_errors=True)
    return jsonify(ok=True)


if __name__ == "__main__":
    print(f"PhotoChronicle {APP_VERSION} is running at http://127.0.0.1:8765")
    print("Press Ctrl+C to stop the server.")
    app.run(host="127.0.0.1", port=8765, debug=False, threaded=True)
