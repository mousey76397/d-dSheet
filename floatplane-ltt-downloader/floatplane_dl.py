#!/usr/bin/env python3
"""Download the back catalogue of a Floatplane creator's video posts (default: Linus Tech Tips).

Requires an active Floatplane subscription to the target creator's content.
See README.md for authentication setup.
"""

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

API_BASE = "https://www.floatplane.com/api"

# Floatplane's own API only requires a reCAPTCHA token for browser-style clients;
# a non-browser User-Agent (e.g. containing "CFNetwork", as their mobile apps use)
# is exempt. This is documented behavior, not a captcha bypass.
DEFAULT_UA = "FloatplaneLTTDownloader/1.0 (CFNetwork)"

CHUNK_SIZE = 1024 * 1024
MAX_RATE_LIMIT_RETRIES = 30
CONNECTION_ERROR_RETRIES = 6
CONNECTION_ERROR_BACKOFF = 10.0

# Floatplane's Retry-After on a 429 counts down to one fixed reset point in
# time, not a fresh penalty per request, so it's honored as reported (up to
# a generous safety ceiling, RATE_LIMIT_WAIT_CEILING, purely against a
# broken/huge header value) rather than capped low and retried sooner - that
# was tried and made things worse, burning through the retry budget while
# the window was still live.
#
# But honoring it wasn't sufficient either: even before that, the pattern
# reported was "wait the first (large) value, then several more 429s with
# small/near-zero Retry-After before it actually clears" - a flaky tail
# right at the edge of the window, likely clock skew between us and
# whichever edge node answers next. A flat small floor there just hammers
# through the retry budget just as fast. So the floor escalates with each
# consecutive rate-limit hit on this call (RATE_LIMIT_MIN_WAIT *
# rate_limit_attempts, capped at RATE_LIMIT_ESCALATION_CEILING) to actually
# ride out that tail, and the retry budget is generous enough for that
# escalation to matter.
RATE_LIMIT_WAIT_CEILING = 600
RATE_LIMIT_MIN_WAIT = 5
RATE_LIMIT_ESCALATION_CEILING = 60

# Every API call is spaced out by a random delay in this range rather than a
# fixed interval, both to stay under whatever Floatplane's real (undocumented,
# unknown) rate limit actually is, and because a fixed period between requests
# is itself a very machine-like pattern - a video-by-video scripted crawl
# looks nothing like a human clicking around regardless of the exact delay,
# but randomizing it is a cheap, low-risk thing to do on top of the pacing we
# already need. This applies between any two calls, not just delivery/info -
# it used to be two separate fixed intervals (one for delivery/info, one for
# post listing) tuned individually; a single random-jittered pace covers both
# and any other call through the same code path.
REQUEST_JITTER_RANGE = (2.0, 10.0)

DRY_RUN_MAX_RATE_LIMIT_WAIT = 20

FAILED_MANIFEST_NAME = "failed_downloads.json"


class FloatplaneError(Exception):
    pass


class RateLimited(FloatplaneError):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, Retry-After={retry_after}s")


def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name.strip().rstrip(".") or "untitled"


def human_size(num_bytes: float) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def parse_rate_limit(s: str) -> float:
    """Parse a rate like '500K', '2M', '1.5G', or a plain byte count, into bytes/sec."""
    s = s.strip().upper()
    multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3}
    if s and s[-1] in multipliers:
        value, mult = s[:-1], multipliers[s[-1]]
    else:
        value, mult = s, 1
    try:
        rate = float(value) * mult
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid rate '{s}', expected e.g. 500K, 2M, 1.5G, or a byte count")
    if rate <= 0:
        raise argparse.ArgumentTypeError("rate limit must be greater than zero")
    return rate


class FloatplaneClient:
    def __init__(self, cookie: str | None = None, user_agent: str = DEFAULT_UA):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        if cookie:
            self.session.cookies.set("sails.sid", cookie, domain=".floatplane.com")
        self._last_request_time = 0.0

    def _get(self, path: str, max_wait: float | None = None, **params):
        url = f"{API_BASE}{path}"
        elapsed = time.monotonic() - self._last_request_time
        jitter = random.uniform(*REQUEST_JITTER_RANGE)
        if elapsed < jitter:
            time.sleep(jitter - elapsed)

        conn_error_attempts = 0
        rate_limit_attempts = 0
        while True:
            try:
                r = self.session.get(url, params=params, timeout=30)
                self._last_request_time = time.monotonic()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                conn_error_attempts += 1
                if conn_error_attempts >= CONNECTION_ERROR_RETRIES:
                    raise FloatplaneError(
                        f"Network error talking to Floatplane on {path} after "
                        f"{CONNECTION_ERROR_RETRIES} attempts: {e}"
                    )
                wait = CONNECTION_ERROR_BACKOFF * conn_error_attempts
                print(f"  Network error on {path} ({e.__class__.__name__}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            if r.status_code == 429:
                rate_limit_attempts += 1
                if rate_limit_attempts >= MAX_RATE_LIMIT_RETRIES:
                    raise FloatplaneError(f"Repeated rate limiting on {path} after {MAX_RATE_LIMIT_RETRIES} attempts, giving up")
                reported_wait = int(r.headers.get("Retry-After", 5))
                if max_wait is not None and reported_wait > max_wait:
                    raise RateLimited(reported_wait)
                escalating_floor = min(RATE_LIMIT_MIN_WAIT * rate_limit_attempts, RATE_LIMIT_ESCALATION_CEILING)
                wait = max(min(reported_wait, RATE_LIMIT_WAIT_CEILING), escalating_floor)
                print(f"  Rate limited by Floatplane, waiting {wait}s (attempt {rate_limit_attempts})...", file=sys.stderr)
                time.sleep(wait)
                continue
            if not r.ok:
                hint = ""
                if r.status_code in (401, 403):
                    hint = (
                        " Your cookie may be expired/invalid, or your account's subscription "
                        "doesn't cover this creator/channel's content."
                    )
                raise FloatplaneError(f"Floatplane returned {r.status_code} for {path}.{hint}")
            return r.json()

    def login(self, username: str, password: str) -> None:
        r = self.session.post(f"{API_BASE}/v2/auth/login", json={"username": username, "password": password})
        if r.status_code == 401:
            raise FloatplaneError("Login failed: invalid username or password.")
        if r.status_code == 400 and "captcha" in r.text.lower():
            raise FloatplaneError(
                "Floatplane is requiring a captcha for this login. "
                "Use --cookie instead (see README.md)."
            )
        r.raise_for_status()
        data = r.json()
        if data.get("needs2FA"):
            token = input("Enter your Floatplane 2FA code: ").strip()
            r2 = self.session.post(f"{API_BASE}/v2/auth/checkFor2faLogin", json={"token": token})
            if r2.status_code == 401:
                raise FloatplaneError("2FA code rejected.")
            r2.raise_for_status()

    def verify_session(self) -> None:
        r = self.session.get(f"{API_BASE}/v3/user/self", timeout=30)
        if r.status_code in (401, 403):
            raise FloatplaneError(
                f"Not authenticated ({r.status_code}). Your cookie may be expired/invalid, login may "
                "have failed, or Floatplane's edge is blocking this client. "
                "See README.md for how to obtain a fresh sails.sid cookie."
            )
        r.raise_for_status()

    def get_creator(self, urlname: str) -> dict:
        data = self._get("/v3/creator/named", creatorURL=urlname)
        if not data:
            raise FloatplaneError(f"Creator '{urlname}' not found.")
        return data[0]

    def resolve_channel(self, creator: dict, channel_urlname: str) -> dict:
        """Resolve a sub-channel URL name (e.g. 'fpexclusive') to its channel dict.

        Sub-channels (Main, Behind the Scenes, FP Exclusive, ...) are not
        separate creators - they're listed under the creator's own 'channels'.
        """
        channels = creator.get("channels") or []
        for channel in channels:
            if channel.get("urlname", "").lower() == channel_urlname.lower():
                return channel
        available = ", ".join(c.get("urlname", "?") for c in channels) or "none"
        raise FloatplaneError(
            f"Channel '{channel_urlname}' not found under creator '{creator.get('urlname')}'. "
            f"Available channels: {available}"
        )

    def iter_posts(
        self,
        creator_id: str,
        page_size: int = 20,
        from_date: str | None = None,
        to_date: str | None = None,
        channel_id: str | None = None,
    ):
        fetch_after = 0
        while True:
            params = {"id": creator_id, "limit": page_size, "fetchAfter": fetch_after, "sort": "ASC"}
            if from_date:
                params["fromDate"] = from_date
            if to_date:
                params["toDate"] = to_date
            if channel_id:
                params["channel"] = channel_id
            batch = self._get("/v3/content/creator", **params)
            if not batch:
                return
            yield from batch
            if len(batch) < page_size:
                return
            fetch_after += page_size

    def delivery_info(self, entity_id: str, max_wait: float | None = None) -> dict:
        return self._get("/v3/delivery/info", max_wait=max_wait, scenario="download", entityId=entity_id)


def pick_variant(delivery: dict, preferred_label: str | None):
    candidates = []
    for group in delivery.get("groups", []):
        group_origin = None
        if group.get("origins"):
            group_origin = group["origins"][0]["url"]
        for variant in group.get("variants", []):
            variant_origin = None
            if variant.get("origins"):
                variant_origin = variant["origins"][0]["url"]
            base = variant_origin or group_origin or "https://www.floatplane.com"
            candidates.append((variant, base))

    if not candidates:
        return None

    if preferred_label:
        for variant, base in candidates:
            if variant.get("label", "").lower() == preferred_label.lower():
                return variant, base
        print(
            f"  WARNING: requested quality '{preferred_label}' not available, "
            "falling back to highest quality.",
            file=sys.stderr,
        )

    candidates.sort(key=lambda vb: vb[0].get("order", 0), reverse=True)
    return candidates[0]


def resolve_url(variant: dict, base: str) -> str:
    url = variant["url"]
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return base.rstrip("/") + "/" + url.lstrip("/")


def download_file(session: requests.Session, url: str, dest: Path, rate_limit: float | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")

    resume_pos = tmp.stat().st_size if tmp.exists() else 0
    headers = {"Referer": "https://www.floatplane.com/"}
    if resume_pos:
        headers["Range"] = f"bytes={resume_pos}-"

    # Keep chunks roughly ~0.5s worth of data at the configured rate, so the
    # sleep-based throttle below is smooth rather than bursty at low rates.
    chunk_size = CHUNK_SIZE if not rate_limit else max(16 * 1024, min(CHUNK_SIZE, int(rate_limit / 2)))

    with session.get(url, headers=headers, stream=True, timeout=60) as r:
        if resume_pos and r.status_code == 416:
            tmp.rename(dest)
            return
        r.raise_for_status()
        mode = "ab" if resume_pos and r.status_code == 206 else "wb"
        if mode == "wb":
            resume_pos = 0
        total = resume_pos + int(r.headers.get("Content-Length", 0))
        downloaded = resume_pos
        last_print = 0.0
        throttle_start = time.monotonic()
        throttled_bytes = 0
        with open(tmp, mode) as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                throttled_bytes += len(chunk)

                if rate_limit:
                    expected_elapsed = throttled_bytes / rate_limit
                    actual_elapsed = time.monotonic() - throttle_start
                    if expected_elapsed > actual_elapsed:
                        time.sleep(expected_elapsed - actual_elapsed)

                now = time.time()
                if total and now - last_print > 1:
                    pct = downloaded / total * 100
                    print(f"\r  {pct:5.1f}%  ({downloaded / 1e6:.1f} / {total / 1e6:.1f} MB)", end="", file=sys.stderr)
                    last_print = now
        print(file=sys.stderr)
    tmp.rename(dest)


def download_thumbnail(session: requests.Session, thumbnail: dict | None, dest: Path) -> None:
    """Save a post's thumbnail next to its video as <video-basename>.jpg -
    Plex (and most other media managers) pick up a same-named image file
    next to a video as that episode's local artwork automatically, with no
    online metadata matching required.
    """
    if not thumbnail or not thumbnail.get("path"):
        return
    ext = Path(urlparse(thumbnail["path"]).path).suffix or ".jpg"
    thumb_dest = dest.with_suffix(ext)
    if thumb_dest.exists():
        return
    try:
        r = session.get(thumbnail["path"], timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  WARNING: could not fetch thumbnail for {dest.name}: {e}", file=sys.stderr)
        return
    try:
        thumb_dest.parent.mkdir(parents=True, exist_ok=True)
        thumb_dest.write_bytes(r.content)
    except OSError as e:
        print(f"  WARNING: could not save thumbnail for {dest.name}: {e}", file=sys.stderr)


def load_failed_manifest(out_root: Path) -> list[dict]:
    path = out_root / FAILED_MANIFEST_NAME
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def update_failed_manifest(out_root: Path, new_failures: list[dict]) -> list[dict]:
    """Merge new_failures into the existing manifest, dropping any entry whose
    file has since actually appeared on disk (downloaded some other way, e.g.
    a prior --retry-failed run), and write the result back."""
    by_video_id = {e["video_id"]: e for e in load_failed_manifest(out_root)}
    for entry in new_failures:
        by_video_id[entry["video_id"]] = entry
    remaining = [e for e in by_video_id.values() if not Path(e["dest"]).exists()]

    path = out_root / FAILED_MANIFEST_NAME
    if not remaining:
        if path.exists():
            path.unlink()
        return remaining
    out_root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(remaining, indent=2))
    return remaining


def find_partial_downloads(out_root: Path) -> list[Path]:
    if not out_root.exists():
        return []
    return sorted(out_root.rglob("*.part"))


VIDEO_ID_RE = re.compile(r"\[([^\[\]]+)\]\.mp4$")


def video_id_from_filename(fname: str) -> str | None:
    """Recover the video id embedded in a "...[id].mp4" filename, e.g. to
    resume a leftover .part file without needing to re-list the catalogue."""
    m = VIDEO_ID_RE.search(fname)
    return m.group(1) if m else None


def top_up_video_interval(args, video_start: float) -> None:
    """Pad the time spent on a real download up to --min-video-interval.

    A big file's own download time already provides natural spacing before
    the next video's delivery-info call; a small file finishes almost
    instantly and removes that spacing entirely, which is when Floatplane's
    rate limit on that endpoint tends to bite. Only called on the real
    (non dry-run) download path - dry-run has its own separate, faster-
    failing mitigation for the same endpoint since it never downloads
    anything to naturally pace against.
    """
    if args.min_video_interval <= 0:
        return
    remaining = args.min_video_interval - (time.monotonic() - video_start)
    if remaining > 0:
        time.sleep(remaining)


def attempt_video(
    client: FloatplaneClient, args, video_id: str, fname: str, dest: Path, state: dict, thumbnail: dict | None = None
) -> None:
    """Size-check (dry run) or download one video. Mutates `state`:
    sizes_disabled (bool), total_bytes/total_unknown (dry-run counters),
    and failed (list of {video_id, fname, dest, reason} dicts, real runs only).
    `thumbnail` is the post's thumbnail ImageModel dict, if the caller has
    it (only the normal per-post loop does - the retry-failed and
    partial-resume passes don't track it, so they just skip this).
    """
    if dest.exists():
        print(f"Skip (already downloaded): {fname}")
        if not args.dry_run and not args.no_thumbnails:
            download_thumbnail(client.session, thumbnail, dest)
        return

    if args.dry_run and state["sizes_disabled"]:
        state["total_unknown"] += 1
        print(f"Would download: {fname}  (size unknown - skipping lookups after rate limit)")
        return

    video_start = time.monotonic()
    try:
        delivery = client.delivery_info(video_id, max_wait=DRY_RUN_MAX_RATE_LIMIT_WAIT if args.dry_run else None)
    except RateLimited as e:
        state["sizes_disabled"] = True
        state["total_unknown"] += 1
        print(
            f"  Floatplane asked to wait {e.retry_after}s on a size lookup - that's "
            "longer than a dry run should block for, so size lookups are disabled for "
            "the rest of this run (filenames will still list, just without sizes).",
            file=sys.stderr,
        )
        print(f"Would download: {fname}  (size unknown - rate limited)")
        return
    except FloatplaneError as e:
        print(f"  WARNING: could not fetch delivery info for {video_id}: {e}", file=sys.stderr)
        if not args.dry_run:
            state["failed"].append(
                {"video_id": video_id, "fname": fname, "dest": str(dest), "reason": f"delivery info: {e}"}
            )
            top_up_video_interval(args, video_start)
        return

    picked = pick_variant(delivery, args.quality)
    if not picked:
        print(f"  WARNING: no downloadable variant for {video_id} ({fname})", file=sys.stderr)
        if not args.dry_run:
            state["failed"].append(
                {"video_id": video_id, "fname": fname, "dest": str(dest), "reason": "no downloadable variant"}
            )
            top_up_video_interval(args, video_start)
        return

    variant, base = picked
    url = resolve_url(variant, base)
    if urlparse(url).path in ("", "/") and not urlparse(url).query:
        print(
            f"  WARNING: resolved URL for {video_id} is just a bare origin ({url}) - "
            "Floatplane's delivery response likely doesn't match what this script "
            f"expects anymore. Raw variant JSON: {json.dumps(variant)}",
            file=sys.stderr,
        )

    if args.dry_run:
        size = variant.get("meta", {}).get("common", {}).get("size")
        if size:
            state["total_bytes"] += size
            print(f"Would download: {fname}  ({human_size(size)})  [{variant.get('label', '?')}]")
        else:
            state["total_unknown"] += 1
            print(f"Would download: {fname}  (size unknown)  [{variant.get('label', '?')}]")
        return

    print(f"Downloading: {fname}  [{variant.get('label', '?')}]")
    try:
        download_file(client.session, url, dest, rate_limit=args.limit_rate)
        if not args.no_thumbnails:
            download_thumbnail(client.session, thumbnail, dest)
    except (requests.RequestException, OSError) as e:
        print(f"  ERROR downloading {fname}: {e}", file=sys.stderr)
        state["failed"].append(
            {"video_id": video_id, "fname": fname, "dest": str(dest), "reason": f"download error: {e}"}
        )
    top_up_video_interval(args, video_start)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--creator",
        default="linustechtips",
        help="Comma-separated Floatplane creator URL name(s), each a separate LMG account. "
        "Includes: linustechtips, techlinked, techquickie, "
        "shortcircuit, channelsuperfun, gamerslexicon. Default: linustechtips. "
        "Not the same as a creator's sub-channels (e.g. LTT's fpexclusive) - see --channel.",
    )
    p.add_argument("--output", default="./floatplane-downloads", help="Output directory")
    p.add_argument(
        "--channel",
        default=None,
        help="Only download posts from this sub-channel of the creator, e.g. 'fpexclusive' for "
        "LTT's Floatplane Exclusive content. Sub-channels (Main, Behind the Scenes, FP Exclusive, "
        "Livestreams, ...) live under a single creator, unlike --creator which selects between "
        "separate LMG creator accounts (linustechtips, techlinked, ...). Applied to every creator "
        "given via --creator; run separately per creator if their channel lists differ.",
    )
    p.add_argument(
        "--cookie",
        default=os.environ.get("FLOATPLANE_SID"),
        help="sails.sid cookie value from a logged-in browser session (recommended, avoids captcha entirely). "
        "Can also be set via the FLOATPLANE_SID env var.",
    )
    p.add_argument("--username", default=os.environ.get("FLOATPLANE_USER"))
    p.add_argument("--password", default=os.environ.get("FLOATPLANE_PASS"))
    p.add_argument("--quality", default=None, help="Preferred quality label, e.g. 1080p, 4K. Falls back to highest available.")
    p.add_argument("--limit", type=int, default=None, help="Max number of posts to process per creator (for testing)")
    p.add_argument("--from-date", default=None, help="ISO 8601 date; only posts released on/after this date")
    p.add_argument("--to-date", default=None, help="ISO 8601 date; only posts released on/before this date")
    p.add_argument("--dry-run", action="store_true", help="List what would be downloaded without downloading")
    p.add_argument(
        "--limit-rate",
        type=parse_rate_limit,
        default=None,
        help="Cap download bandwidth, e.g. 500K, 2M, 1.5G (bytes/sec). "
        "Useful for a slow background run that shouldn't hog your connection.",
    )
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="Ignore --creator/--channel/--from-date/--to-date/--limit and instead retry just the "
        "files recorded as failed or skipped in <output>/failed_downloads.json from a previous run, "
        "without re-listing the whole catalogue.",
    )
    p.add_argument(
        "--min-video-interval",
        type=float,
        default=15.0,
        help="Minimum seconds spent per video before moving to the next one, on real downloads only "
        "(0 disables this). A big file's own download time already spaces out how often Floatplane's "
        "per-video delivery-info lookup gets hit; a small file finishes almost instantly and removes "
        "that spacing, which is when that endpoint tends to get rate-limited. Small files get padded "
        "with idle time up to this floor; big files that already take longer than this aren't slowed "
        "down further. This is unrelated to --limit-rate, which caps the download's own byte-transfer "
        "speed rather than the gap between videos.",
    )
    p.add_argument(
        "--no-thumbnails",
        action="store_true",
        help="Don't save each post's thumbnail image alongside its video. By default, "
        "<video-basename>.jpg is saved next to each video (backfilling existing files too) - most "
        "media managers, including Plex, pick up a same-named image next to a video as that "
        "episode's local artwork automatically, with no online metadata matching required.",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if not args.cookie and not (args.username and args.password):
        print(
            "ERROR: provide either --cookie (recommended, see README.md) "
            "or both --username and --password.",
            file=sys.stderr,
        )
        sys.exit(2)

    client = FloatplaneClient(cookie=args.cookie)
    try:
        if args.cookie:
            client.verify_session()
        else:
            client.login(args.username, args.password)
    except FloatplaneError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    out_root = Path(args.output)
    grand_total_bytes = 0
    grand_total_unknown = 0
    state = {"sizes_disabled": False, "total_bytes": 0, "total_unknown": 0, "failed": []}

    if args.retry_failed:
        manifest = load_failed_manifest(out_root)
        if not manifest:
            print(f"No failed downloads recorded in {out_root / FAILED_MANIFEST_NAME}.")
        else:
            print(f"\n== Retrying {len(manifest)} previously failed/skipped file(s) ==")
            for entry in manifest:
                attempt_video(client, args, entry["video_id"], entry["fname"], Path(entry["dest"]), state)
    else:
        for creator_name in [c.strip() for c in args.creator.split(",") if c.strip()]:
            try:
                creator = client.get_creator(creator_name)
                channel = client.resolve_channel(creator, args.channel) if args.channel else None
                channel_id = channel["id"] if channel else None
            except FloatplaneError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                continue

            label = f"{creator['title']} ({creator_name})"
            if channel:
                label += f" / {channel.get('title', args.channel)}"
            print(f"\n== {label} ==")
            out_dir = out_root / sanitize(creator["title"])
            if channel:
                new_channel_dir = sanitize(channel.get("title") or args.channel)
                old_channel_dir = sanitize(args.channel)
                new_out_dir = out_dir / new_channel_dir
                old_out_dir = out_dir / old_channel_dir
                if old_channel_dir != new_channel_dir and old_out_dir.exists() and not new_out_dir.exists():
                    old_out_dir.rename(new_out_dir)
                    print(
                        f"Renamed existing '{old_out_dir}' to '{new_out_dir}' to match Floatplane's "
                        "real channel title, instead of the raw --channel URL name used before - "
                        "this keeps every already-downloaded file recognized as done rather than "
                        "re-downloading the whole channel."
                    )
                out_dir = new_out_dir
            print(f"Output folder: {out_dir}")
            processed = 0
            state["total_bytes"] = 0
            state["total_unknown"] = 0

            try:
                for post in client.iter_posts(
                    creator["id"], from_date=args.from_date, to_date=args.to_date, channel_id=channel_id
                ):
                    if args.limit and processed >= args.limit:
                        break
                    processed += 1

                    video_ids = post.get("videoAttachments") or []
                    if not video_ids:
                        continue

                    date_str = (post.get("releaseDate") or "")[:10]
                    title = sanitize(post["title"])

                    for i, video_id in enumerate(video_ids):
                        suffix = f" (part {i + 1})" if len(video_ids) > 1 else ""
                        fname = f"{date_str} - {title}{suffix} [{video_id}].mp4"
                        dest = out_dir / fname
                        attempt_video(client, args, video_id, fname, dest, state, thumbnail=post.get("thumbnail"))
            except FloatplaneError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                continue

            summary = f"-- {creator['title']}: processed {processed} post(s)"
            if args.dry_run:
                summary += f", estimated {human_size(state['total_bytes'])} to download"
                if state["total_unknown"]:
                    summary += f" ({state['total_unknown']} file(s) of unknown size not included)"
                grand_total_bytes += state["total_bytes"]
                grand_total_unknown += state["total_unknown"]
            print(summary + " --")

        if args.dry_run and len([c for c in args.creator.split(",") if c.strip()]) > 1:
            total_line = f"\n== Total estimated download size: {human_size(grand_total_bytes)} =="
            if grand_total_unknown:
                total_line += f" ({grand_total_unknown} file(s) of unknown size not included)"
            print(total_line)

    if not args.dry_run:
        partials = find_partial_downloads(out_root)
        if partials:
            print(f"\n== Resuming {len(partials)} unfinished (partial) download(s) ==")
            for p in partials:
                dest = p.with_suffix("")  # "...[id].mp4.part" -> "...[id].mp4"
                fname = dest.name
                video_id = video_id_from_filename(fname)
                if not video_id:
                    print(f"  WARNING: couldn't recover a video id from {fname}, leaving it as-is", file=sys.stderr)
                    continue
                attempt_video(client, args, video_id, fname, dest, state)

        remaining_failed = update_failed_manifest(out_root, state["failed"])
        if remaining_failed:
            print(f"\n== {len(remaining_failed)} file(s) failed or were skipped due to errors ==")
            for entry in remaining_failed:
                print(f"  {entry['fname']}  ({entry['reason']})")
            print(f"Recorded in {out_root / FAILED_MANIFEST_NAME} - re-run with --retry-failed to retry just these.")

        still_partial = find_partial_downloads(out_root)
        if still_partial:
            print(f"\n== {len(still_partial)} download(s) still unfinished after retrying ==")
            for p in still_partial:
                print(f"  {p.relative_to(out_root)}  ({human_size(p.stat().st_size)} so far)")
            print("Re-run the same command (or --retry-failed) to keep trying.")
    else:
        partials = find_partial_downloads(out_root)
        if partials:
            print(f"\n== {len(partials)} unfinished (partial) download(s) ==")
            for p in partials:
                print(f"  {p.relative_to(out_root)}  ({human_size(p.stat().st_size)} so far)")
            print("A real (non --dry-run) run will resume these automatically.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Re-run the same command to resume.", file=sys.stderr)
        sys.exit(130)
