#!/usr/bin/env python3
"""Prepare and safely publish one daily text Tips card (Python 3.9+).

Dependencies for rendering only: Pillow, playwright, installed Chromium.
This CLI does not install dependencies, schedule jobs, or run git. The scheduler
should invoke it daily at 10:00 Asia/Shanghai and supply a curated draft JSON.
Draft fields: date, cat, sourceDate, sourceTitle, title, one, points (exactly
three strings), caution (may be empty), evidence (list of {title, url}, may be
empty). All other draft fields are rejected; publication metadata is generated.

The marked index.html block must independently define tipsDrawCard(d, canvas)
and return either [] or an object with errors: []. No alternate painter is used.
Temporary artifacts are deliberately retained; this script never deletes files.
"""

import argparse
import base64
import copy
import datetime as dt
import fcntl
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import unicodedata
from contextlib import contextmanager
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
START = dt.date(2026, 10, 12)
SCHEDULE = {
    "time": "10:00",
    "timezone": "Asia/Shanghai",
    "rotation": "fit-look",
    "startDate": START.isoformat(),
}
BASE_FIELDS = {
    "date", "cat", "sourceDate", "sourceTitle", "title", "one", "points",
    "caution", "evidence",
}
META_FIELDS = {"generatedAt", "png"}
DRAW_BEGIN = "  // TIPS_DRAW_BEGIN"
DRAW_END = "  // TIPS_DRAW_END"
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
HTML_RE = re.compile(r"<\s*(?:/?\s*[A-Za-z]|[!?])")


class TipsError(Exception):
    """A validation or safe-publication failure."""


def now_shanghai():
    return dt.datetime.now(TZ)


def parse_date(value, label="date"):
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise TipsError("{} must be YYYY-MM-DD".format(label))
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise TipsError("{} is not a real calendar date".format(label))


def planned_category(day):
    return "fit" if (day - START).days % 2 == 0 else "look"


def safe_text(value, label, limit=None, required=True):
    if not isinstance(value, str):
        raise TipsError("{} must be a string, not coerced data".format(label))
    if required and not value.strip():
        raise TipsError("{} must not be blank".format(label))
    if limit is not None and len(value) > limit:
        raise TipsError("{} exceeds {} characters".format(label, limit))
    decoded = value
    # Detect HTML even when entity-encoded; never transform the published text.
    for _ in range(8):
        if HTML_RE.search(decoded):
            raise TipsError("{} contains HTML or markup".format(label))
        if any(unicodedata.category(c) in ("Cc", "Cf", "Cs")
               and c not in ("\n", "\t") for c in decoded):
            raise TipsError("{} contains unsafe control characters".format(label))
        next_value = html.unescape(decoded)
        if next_value == decoded:
            return value
        decoded = next_value
    raise TipsError("{} has excessively nested HTML entities".format(label))


def source_title_key(title):
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
            + "\n").encode("utf-8")


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TipsError("JSON contains a duplicate object key")
        result[key] = value
    return result


def reject_constant(value):
    raise TipsError("JSON contains a non-finite number: {}".format(value))


def decode_json(raw, label):
    try:
        return json.loads(raw, object_pairs_hook=strict_object,
                          parse_constant=reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise TipsError("Invalid JSON in {}: {}".format(label, str(exc)[:200]))


def read_json(path):
    try:
        return decode_json(path.read_bytes(), str(path))
    except OSError as exc:
        raise TipsError("Cannot read {}: {}".format(path, exc.strerror))


def repo_path(value):
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise TipsError("Cannot resolve repository: {}".format(str(exc)[:200]))
    if not path.is_dir():
        raise TipsError("--repo must name an existing directory")
    return path


def require_regular(path, optional=False):
    if path.is_symlink():
        raise TipsError("Refusing symlink: {}".format(path))
    if not path.exists():
        if optional:
            return
        raise TipsError("Missing required file: {}".format(path))
    if not path.is_file():
        raise TipsError("Not a regular file: {}".format(path))


@contextmanager
def repo_lock(repo):
    # Stable per real repository and user, outside the git working tree.
    digest = hashlib.sha256(os.fsencode(str(repo))).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / (
        "daily-tips-{}-{}.lock".format(os.getuid(), digest))
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(lock_path), flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise TipsError("Lock is not a regular file owned by this user")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def validate_fields(record, stored=False):
    if not isinstance(record, dict):
        raise TipsError("record must be a JSON object")
    allowed = BASE_FIELDS | META_FIELDS if stored else BASE_FIELDS
    if set(record) != allowed:
        missing = sorted(allowed - set(record))
        extra = sorted(set(record) - allowed)
        raise TipsError("record fields mismatch; missing={}, extra={}".format(
            missing, extra))
    day = parse_date(record["date"])
    source_day = parse_date(record["sourceDate"], "sourceDate")
    if record["cat"] != planned_category(day):
        raise TipsError("Wrong rotation: {} requires {}".format(
            day, planned_category(day)))
    if day > now_shanghai().date():
        raise TipsError("Publication date is in the future in Asia/Shanghai")
    if source_day > day:
        raise TipsError("sourceDate must be no later than publication date")
    safe_text(record["sourceTitle"], "sourceTitle")
    safe_text(record["title"], "title", 32)
    safe_text(record["one"], "one", 55)
    points = record["points"]
    if not isinstance(points, list) or len(points) != 3:
        raise TipsError("points must contain exactly three strings")
    for i, point in enumerate(points):
        safe_text(point, "points[{}]".format(i), 42)
    safe_text(record["caution"], "caution", 72, required=False)
    evidence = record["evidence"]
    if not isinstance(evidence, list):
        raise TipsError("evidence must be an array (possibly empty)")
    for i, item in enumerate(evidence):
        if not isinstance(item, dict) or set(item) != {"title", "url"}:
            raise TipsError("evidence[{}] must have exactly title and url".format(i))
        safe_text(item["title"], "evidence title")
        url = safe_text(item["url"], "evidence URL")
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in ("http", "https") and parsed.hostname
                     and not parsed.username and not parsed.password)
            parsed.port  # Reject malformed port values.
        except ValueError:
            valid = False
        if not valid or any(c.isspace() for c in url) or "\\" in url:
            raise TipsError("evidence URL must be a safe absolute HTTP(S) URL")
    if stored:
        safe_text(record["generatedAt"], "generatedAt")
        try:
            stamp = dt.datetime.fromisoformat(record["generatedAt"])
        except ValueError:
            raise TipsError("generatedAt is not an ISO timestamp")
        if stamp.utcoffset() != dt.timedelta(hours=8):
            raise TipsError("generatedAt must carry the Asia/Shanghai UTC+08:00 offset")
        if record["png"] != "tips/{}.png".format(record["date"]):
            raise TipsError("Stored PNG path does not match publication date")
    return day


def load_manifest(repo):
    path = repo / "tips.json"
    require_regular(path, optional=True)
    raw = path.read_bytes() if path.exists() else None
    data = decode_json(raw, str(path)) if raw is not None else {}
    if data == {}:
        data = {"version": 1, "schedule": dict(SCHEDULE), "entries": {}}
    if (not isinstance(data, dict)
            or set(data) != {"version", "schedule", "entries"}
            or type(data["version"]) is not int or data["version"] != 1
            or data["schedule"] != SCHEDULE
            or not isinstance(data["entries"], dict)):
        raise TipsError("tips.json must be the version-1 fit-look manifest")
    used_pairs, used_titles = set(), set()
    for key, record in data["entries"].items():
        parse_date(key, "entries key")
        validate_fields(record, stored=True)
        if record["date"] != key:
            raise TipsError("Manifest entry date/key mismatch")
        pair = (record["sourceDate"], record["sourceTitle"])
        title_key = source_title_key(record["sourceTitle"])
        if pair in used_pairs or title_key in used_titles:
            raise TipsError("Manifest already contains duplicate published sources")
        used_pairs.add(pair)
        used_titles.add(title_key)
    return data, raw


def source_rows(sync, target):
    if not isinstance(sync, dict):
        raise TipsError("sync.json must be a top-level object")
    dates = []
    # Only real top-level YYYY-MM-DD keys are traversed, never metadata trees.
    for key in sync:
        if not isinstance(key, str) or not DATE_RE.fullmatch(key):
            continue
        try:
            day = parse_date(key, "sync date")
        except TipsError:
            continue
        if day <= target:
            dates.append(key)
    for date_key in sorted(dates, reverse=True):
        row = sync[date_key]
        if not isinstance(row, dict):
            continue
        append = row.get("kbAppend")
        if isinstance(append, dict):
            groups = ((cat, items) for cat, items in append.items()
                      if cat in ("fit", "look") and isinstance(items, list))
        elif isinstance(append, list):
            groups = ((item.get("category") or item.get("cat"), [item])
                      for item in append if isinstance(item, dict))
        else:
            continue
        for cat, items in groups:
            if cat not in ("fit", "look"):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    title = safe_text(item.get("title"), "source title")
                    one = safe_text(item.get("one"), "source one")
                    points = item.get("points")
                    if not isinstance(points, list) or not points:
                        continue
                    for point in points:
                        safe_text(point, "source point")
                except TipsError:
                    continue
                actual_date = item.get("_date") or date_key
                try:
                    source_day = parse_date(actual_date, "source _date")
                except TipsError:
                    continue
                if source_day > target:
                    continue
                source = {"sourceDate": actual_date, "cat": cat, "title": title,
                          "one": one, "points": list(points)}
                if "caution" in item:
                    try:
                        source["caution"] = safe_text(
                            item["caution"], "source caution", 72, required=False)
                    except TipsError:
                        continue
                yield source


def load_sync(repo):
    path = repo / "sync.json"
    require_regular(path)
    return read_json(path)


def used_sources(manifest, excluding_date=None):
    records = [r for day, r in manifest["entries"].items()
               if day != excluding_date]
    return ({(r["sourceDate"], r["sourceTitle"]) for r in records},
            {source_title_key(r["sourceTitle"]) for r in records})


def prepare(repo, day):
    with repo_lock(repo):
        manifest, _ = load_manifest(repo)
        sync = load_sync(repo)
        pairs, titles = used_sources(manifest)
        category = planned_category(day)
        candidates = []
        rows = sorted(source_rows(sync, day), key=lambda item: item["sourceDate"], reverse=True)
        for item in rows:
            key = source_title_key(item["title"])
            pair = (item["sourceDate"], item["title"])
            if item["cat"] != category or pair in pairs or key in titles:
                continue
            # Entire look category is eligible, including clothing and skincare.
            candidates.append(item)
            pairs.add(pair)
            titles.add(key)
            if len(candidates) == 8:
                break
        return {"success": True, "status": "prepared", "date": day.isoformat(),
                "plannedCategory": category,
                "exists": day.isoformat() in manifest["entries"],
                "manifestPath": str(repo / "tips.json"),
                "schedule": dict(SCHEDULE), "candidates": candidates}


def validate_source(draft, sync, day, manifest):
    found = any(item["cat"] == draft["cat"]
                and item["sourceDate"] == draft["sourceDate"]
                and item["title"] == draft["sourceTitle"]
                for item in source_rows(sync, day))
    if not found:
        raise TipsError("Source not found with actual date/category/title in sync.json")
    pairs, titles = used_sources(manifest, excluding_date=draft["date"])
    if ((draft["sourceDate"], draft["sourceTitle"]) in pairs
            or source_title_key(draft["sourceTitle"]) in titles):
        raise TipsError("Source or same-origin title has already been published")


def extract_draw(repo):
    path = repo / "index.html"
    require_regular(path)
    text = path.read_text(encoding="utf-8")
    if text.count(DRAW_BEGIN) != 1 or text.count(DRAW_END) != 1:
        raise TipsError("index.html needs exactly one TIPS_DRAW_BEGIN/END marked block")
    start = text.index(DRAW_BEGIN) + len(DRAW_BEGIN)
    end = text.index(DRAW_END)
    if end <= start:
        raise TipsError("Drawing function markers are reversed")
    block = text[start:end]
    if not re.search(r"\bfunction\s+tipsDrawCard\s*\(", block):
        raise TipsError("Marked block must define global function tipsDrawCard(d, canvas)")
    if re.search(r"</script", block, re.IGNORECASE):
        raise TipsError("Drawing block contains an unexpected closing script tag")
    return block


def verify_png(data):
    try:
        from PIL import Image
    except ImportError:
        raise TipsError("Rendering verification requires Pillow for this Python")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.size != (1080, 1080):
                raise TipsError("PNG must be exactly 1080 x 1080")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except TipsError:
        raise
    except Exception as exc:
        raise TipsError("PNG failed Pillow verification: {}".format(str(exc)[:200]))
    return hashlib.sha256(data).hexdigest()


def write_new(path, data):
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def render(repo, draft, block):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise TipsError("Rendering requires playwright and its installed Chromium")
    # Retain rendering artifacts beside the repo, without polluting its git tree.
    work = Path(tempfile.mkdtemp(prefix=".daily-tips-", dir=str(repo.parent)))
    renderer = work / "renderer.html"
    document = ("<!doctype html><html><head><meta charset='utf-8'>"
                "<meta http-equiv='Content-Security-Policy' content=\""
                "default-src 'none'; script-src 'unsafe-inline'; "
                "style-src 'unsafe-inline'; img-src data:;\">"
                "<title>Tips validation renderer</title></head><body>"
                "<canvas id='tips-canvas' width='1080' height='1080'></canvas>"
                "<script>\n" + block + "\n</script></body></html>")
    write_new(renderer, document.encode("utf-8"))
    try:
        with sync_playwright() as playwright:
            # Use installed Chrome; do not depend on a separately downloaded shell.
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                context = browser.new_context(viewport={"width": 1080, "height": 1080},
                                              device_scale_factor=1)
                page = context.new_page()
                page.set_default_timeout(30000)
                page_errors = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(renderer.as_uri(), wait_until="load", timeout=30000)
                result = page.evaluate("""async (draft) => {
                    await document.fonts.ready;
                    if (typeof tipsDrawCard !== 'function') {
                        throw new Error('tipsDrawCard is not globally available');
                    }
                    const canvas = document.getElementById('tips-canvas');
                    const returned = await tipsDrawCard(draft, canvas);
                    await document.fonts.ready;
                    const errors = Array.isArray(returned) ? returned
                        : (returned && returned.errors);
                    if (!Array.isArray(errors) || errors.length !== 0) {
                        throw new Error('tipsDrawCard requires errors=[]; got ' +
                            JSON.stringify(errors).slice(0, 1000));
                    }
                    if (canvas.width !== 1080 || canvas.height !== 1080) {
                        throw new Error('tipsDrawCard must produce 1080x1080');
                    }
                    return {errors, dataURL: canvas.toDataURL('image/png')};
                }""", draft)
                if page_errors:
                    raise TipsError("Renderer page errors: {}".format(
                        "; ".join(page_errors)[:1000]))
            finally:
                browser.close()
        if not isinstance(result, dict) or result.get("errors") != []:
            raise TipsError("Renderer did not return errors=[]")
        data_url = result.get("dataURL", "")
        prefix = "data:image/png;base64,"
        if not isinstance(data_url, str) or not data_url.startswith(prefix):
            raise TipsError("Canvas did not return a PNG data URL")
        png_bytes = base64.b64decode(data_url[len(prefix):], validate=True)
        sha = verify_png(png_bytes)
        png_path = work / "card.png"
        write_new(png_path, png_bytes)
        return work, png_path, sha
    except Exception as exc:
        raise TipsError("Rendering failed; retained temporary directory {}: {}".format(
            work, str(exc)[:1200]))


def sync_directory(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_unchanged(repo, old_raw):
    path = repo / "tips.json"
    require_regular(path, optional=True)
    current = path.read_bytes() if path.exists() else None
    if current != old_raw:
        raise TipsError("tips.json changed during publication; refusing replacement")


def publish(repo, draft_path, check_only=False):
    draft = read_json(draft_path)
    day = validate_fields(draft)
    with repo_lock(repo):
        manifest, old_raw = load_manifest(repo)
        existing = manifest["entries"].get(draft["date"])
        png_rel = "tips/{}.png".format(draft["date"])
        png_path = repo / png_rel
        tips_dir = repo / "tips"
        if tips_dir.is_symlink() or (tips_dir.exists() and not tips_dir.is_dir()):
            raise TipsError("Refusing non-directory or symlink tips path")
        existing_sha = None
        if existing is not None:
            content = {key: existing[key] for key in BASE_FIELDS}
            if content != draft:
                raise TipsError("Date is already published with different content; no overwrite")
            require_regular(png_path)
            existing_sha = verify_png(png_path.read_bytes())
            if not check_only:
                return {"success": True, "status": "idempotent", "exists": True,
                        "date": draft["date"], "png": str(png_path),
                        "sha256": existing_sha,
                        "manifestSha256": hashlib.sha256(old_raw).hexdigest(),
                        "generatedAt": existing["generatedAt"], "written": [],
                        "filesToCommit": []}
        elif os.path.lexists(str(png_path)):
            raise TipsError("PNG already exists without a record; refusing overwrite: {}".format(
                png_path))
        if existing is None:
            validate_source(draft, load_sync(repo), day, manifest)
        block = extract_draw(repo)
        work, temporary_png, sha = render(repo, draft, block)
        result = {"success": True, "status": "checked" if check_only else "published",
                  "exists": existing is not None, "date": draft["date"],
                  "plannedCategory": draft["cat"], "sha256": sha,
                  "temporaryDirectory": str(work), "errors": [],
                  "filesToCommit": [], "written": []}
        if check_only:
            result["png"] = str(temporary_png)
            if existing_sha is not None:
                result["existingPngSha256"] = existing_sha
            return result
        record = copy.deepcopy(draft)
        record["generatedAt"] = now_shanghai().isoformat(timespec="seconds")
        record["png"] = png_rel
        updated = copy.deepcopy(manifest)
        updated["entries"][draft["date"]] = record
        manifest_data = json_bytes(updated)
        staging_json = work / "tips.json.next"
        write_new(staging_json, manifest_data)
        ensure_unchanged(repo, old_raw)
        tips_dir.mkdir(exist_ok=True)
        if tips_dir.is_symlink() or not tips_dir.is_dir():
            raise TipsError("tips directory changed unexpectedly")
        # Exclusive atomic link, not replace: pre-existing PNGs are never clobbered.
        try:
            os.link(str(temporary_png), str(png_path))
        except FileExistsError:
            raise TipsError("PNG appeared concurrently; refusing overwrite")
        try:
            sync_directory(tips_dir)
            ensure_unchanged(repo, old_raw)
            os.replace(str(staging_json), str(repo / "tips.json"))
            sync_directory(repo)
        except Exception as exc:
            raise TipsError("Publication interrupted after PNG creation; no files deleted. "
                            "Preserved PNG {}; temporary directory {}: {}".format(
                                png_path, work, str(exc)[:300]))
        result.update({"png": str(png_path), "generatedAt": record["generatedAt"],
                       "manifestSha256": hashlib.sha256(manifest_data).hexdigest(),
                       "written": [str(png_path), str(repo / "tips.json")],
                       "filesToCommit": [str(repo / "tips.json"), str(png_path)]})
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="List up to 8 newest unused real KB entries")
    prep.add_argument("--repo", required=True, help="Repository containing sync.json")
    prep.add_argument("--date", help="YYYY-MM-DD; default is today in Asia/Shanghai")
    pub = sub.add_parser("publish", help="Validate a draft and publish exactly one PNG")
    pub.add_argument("--repo", required=True, help="Repository containing index.html/sync.json")
    pub.add_argument("--draft", required=True, help="JSON file with exactly the draft fields")
    pub.add_argument("--check-only", action="store_true",
                     help="Render/verify in retained temp directory only; never publish")
    args = parser.parse_args(argv)
    try:
        repo = repo_path(args.repo)
        if args.command == "prepare":
            day = parse_date(args.date) if args.date else now_shanghai().date()
            result = prepare(repo, day)
        else:
            draft_path = Path(args.draft).expanduser().absolute()
            result = publish(repo, draft_path, args.check_only)
        emit(result)
        return 0
    except (TipsError, OSError, UnicodeError) as exc:
        emit({"success": False, "status": "error", "error": str(exc)[:1800]})
        return 1
    except KeyboardInterrupt:
        emit({"success": False, "status": "interrupted",
              "error": "Interrupted; temporary artifacts were retained; nothing deleted"})
        return 130


if __name__ == "__main__":
    sys.exit(main())
