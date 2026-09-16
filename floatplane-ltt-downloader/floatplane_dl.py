#!/usr/bin/env python3
"""Download the back catalogue of a Floatplane creator's video posts (default: Linus Tech Tips).

Requires an active Floatplane subscription to the target creator's content.
See README.md for authentication setup.
"""

import argparse
import json
import os
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
MAX_RATE_LIMIT_RETRIES = 8
CONNECTION_ERROR_RETRIES = 6
CONNECTION_ERROR_BACKOFF = 10.0

# Floatplane's Retry-After on a 429 counts down to one fixed reset point in
# time, not a fresh penalty per request - asking again sooner just gets back
# a smaller number counting down to that same point, it doesn't move the
# point up. So the wait is honored as reported (up to a generous safety
# ceiling, RATE_LIMIT_WAIT_CEILING, purely against a broken/huge header
# value) rather than capped low and retried sooner - that was tried and
# made things worse: it burns through the retry budget while the window is
# still live and, once the countdown nominally reaches 0 but the server is
# still returning 429 (observed happening for several seconds past 0,
# likely clock skew at the edge of the window), retrying with no floor on
# the wait hammers the endpoint at zero delay. RATE_LIMIT_MIN_WAIT puts a
# floor under that.
RATE_LIMIT_WAIT_CEILING = 600
RATE_LIMIT_MIN_WAIT = 5

# Floatplane's delivery/info endpoint (the one that returns a video's download
# URL and size) throttles much more aggressively than its other endpoints when
# hit back-to-back with no download in between - as dry-run size lookups do.
# Space calls out to stay under that, and cap how long dry-run is willing to
# block on a single 429 before giving up on sizes rather than stalling for
# whatever (large) Retry-After Floatplane sent.
DELIVERY_INFO_MIN_INTERVAL = 2.0
DRY_RUN_MAX_RATE_LIMIT_WAIT = 20

# Post listing (/v3/content/creator) has the same problem: fetching each page
# is normally paced by the time spent downloading that page's videos, but
# once most of a page is already-downloaded and skipped instantly (e.g. a
# repeat run over a mostly-finished back catalogue), pages get requested
# back-to-back with nothing slowing them down, and that alone is enough to
# trip Floatplane's rate limit on this endpoint too.
CONTENT_LISTING_MIN_INTERVAL = 1.5

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
        self._last_delivery_info_call = 0.0
        self._last_listing_call = 0.0

    def _get(self, path: str, max_wait: float | None = None, **params):
        url = f"{API_BASE}{path}"
        conn_error_attempts = 0
        rate_limit_attempts = 0
        while True:
            try:
                r = self.session.get(url, params=params, timeout=30)
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
                wait = int(r.headers.get("Retry-After", 5))
                if max_wait is not None and wait > max_wait:
                    raise RateLimited(wait)
                wait = max(min(wait, RATE_LIMIT_WAIT_CEILING), RATE_LIMIT_MIN_WAIT)
                print(f"  Rate limited by Floatplane, waiting {wait}s...", file=sys.stderr)
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

    def resolve_channel(self, creator: dict, channel_urlname: str) -> str:
        """Resolve a sub-channel URL name (e.g. 'fpexclusive') to its channel id.

        Sub-channels (Main, Behind the Scenes, FP Exclusive, ...) are not
        separate creators - they're listed under the creator's own 'channels'.
        """
        channels = creator.get("channels") or []
        for channel in channels:
            if channel.get("urlname", "").lower() == channel_urlname.lower():
                return channel["id"]
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
            elapsed = time.monotonic() - self._last_listing_call
            if elapsed < CONTENT_LISTING_MIN_INTERVAL:
                time.sleep(CONTENT_LISTING_MIN_INTERVAL - elapsed)
            try:
                batch = self._get("/v3/content/creator", **params)
            finally:
                self._last_listing_call = time.monotonic()
            if not batch:
                return
            yield from batch
            if len(batch) < page_size:
                return
            fetch_after += page_size

    def delivery_info(self, entity_id: str, max_wait: float | None = None) -> dict:
        elapsed = time.monotonic() - self._last_delivery_info_call
        if elapsed < DELIVERY_INFO_MIN_INTERVAL:
            time.sleep(DELIVERY_INFO_MIN_INTERVAL - elapsed)
        try:
            return self._get("/v3/delivery/info", max_wait=max_wait, scenario="download", entityId=entity_id)
        finally:
            self._last_delivery_info_call = time.monotonic()


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


def attempt_video(client: FloatplaneClient, args, video_id: str, fname: str, dest: Path, state: dict) -> None:
    """Size-check (dry run) or download one video. Mutates `state`:
    sizes_disabled (bool), total_bytes/total_unknown (dry-run counters),
    and failed (list of {video_id, fname, dest, reason} dicts, real runs only).
    """
    if dest.exists():
        print(f"Skip (already downloaded): {fname}")
        return

    if args.dry_run and state["sizes_disabled"]:
        state["total_unknown"] += 1
        print(f"Would download: {fname}  (size unknown - skipping lookups after rate limit)")
        return

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
        return

    picked = pick_variant(delivery, args.quality)
    if not picked:
        print(f"  WARNING: no downloadable variant for {video_id} ({fname})", file=sys.stderr)
        if not args.dry_run:
            state["failed"].append(
                {"video_id": video_id, "fname": fname, "dest": str(dest), "reason": "no downloadable variant"}
            )
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
    except (requests.RequestException, OSError) as e:
        print(f"  ERROR downloading {fname}: {e}", file=sys.stderr)
        state["failed"].append(
            {"video_id": video_id, "fname": fname, "dest": str(dest), "reason": f"download error: {e}"}
        )


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
                channel_id = client.resolve_channel(creator, args.channel) if args.channel else None
            except FloatplaneError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                continue

            label = f"{creator['title']} ({creator_name})"
            if args.channel:
                label += f" / {args.channel}"
            print(f"\n== {label} ==")
            out_dir = out_root / sanitize(creator["title"])
            if args.channel:
                out_dir = out_dir / sanitize(args.channel)
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
                        attempt_video(client, args, video_id, fname, dest, state)
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
