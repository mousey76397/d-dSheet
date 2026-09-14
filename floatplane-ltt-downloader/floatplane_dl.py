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
MAX_RATE_LIMIT_RETRIES = 6

# Floatplane's delivery/info endpoint (the one that returns a video's download
# URL and size) throttles much more aggressively than its other endpoints when
# hit back-to-back with no download in between - as dry-run size lookups do.
# Space calls out to stay under that, and cap how long dry-run is willing to
# block on a single 429 before giving up on sizes rather than stalling for
# whatever (large) Retry-After Floatplane sent.
DELIVERY_INFO_MIN_INTERVAL = 2.0
DRY_RUN_MAX_RATE_LIMIT_WAIT = 20


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

    def _get(self, path: str, max_wait: float | None = None, **params):
        url = f"{API_BASE}{path}"
        for attempt in range(MAX_RATE_LIMIT_RETRIES):
            r = self.session.get(url, params=params, timeout=30)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 5))
                if max_wait is not None and wait > max_wait:
                    raise RateLimited(wait)
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
        raise FloatplaneError(f"Repeated rate limiting on {path}, giving up")

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
            batch = self._get("/v3/content/creator", **params)
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
    sizes_disabled = False

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
        creator_total_bytes = 0
        creator_total_unknown = 0

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

                    if dest.exists():
                        print(f"Skip (already downloaded): {fname}")
                        continue

                    if args.dry_run and sizes_disabled:
                        creator_total_unknown += 1
                        print(f"Would download: {fname}  (size unknown - skipping lookups after rate limit)")
                        continue

                    try:
                        delivery = client.delivery_info(
                            video_id, max_wait=DRY_RUN_MAX_RATE_LIMIT_WAIT if args.dry_run else None
                        )
                    except RateLimited as e:
                        sizes_disabled = True
                        creator_total_unknown += 1
                        print(
                            f"  Floatplane asked to wait {e.retry_after}s on a size lookup - that's "
                            "longer than a dry run should block for, so size lookups are disabled for "
                            "the rest of this run (filenames will still list, just without sizes).",
                            file=sys.stderr,
                        )
                        print(f"Would download: {fname}  (size unknown - rate limited)")
                        continue
                    except FloatplaneError as e:
                        print(f"  WARNING: could not fetch delivery info for {video_id}: {e}", file=sys.stderr)
                        continue

                    picked = pick_variant(delivery, args.quality)
                    if not picked:
                        print(f"  WARNING: no downloadable variant for {video_id} ({title})", file=sys.stderr)
                        continue

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
                            creator_total_bytes += size
                            print(f"Would download: {fname}  ({human_size(size)})  [{variant.get('label', '?')}]")
                        else:
                            creator_total_unknown += 1
                            print(f"Would download: {fname}  (size unknown)  [{variant.get('label', '?')}]")
                        continue

                    print(f"Downloading: {fname}  [{variant.get('label', '?')}]")
                    try:
                        download_file(client.session, url, dest, rate_limit=args.limit_rate)
                    except (requests.RequestException, OSError) as e:
                        print(f"  ERROR downloading {fname}: {e}", file=sys.stderr)
        except FloatplaneError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            continue

        summary = f"-- {creator['title']}: processed {processed} post(s)"
        if args.dry_run:
            summary += f", estimated {human_size(creator_total_bytes)} to download"
            if creator_total_unknown:
                summary += f" ({creator_total_unknown} file(s) of unknown size not included)"
            grand_total_bytes += creator_total_bytes
            grand_total_unknown += creator_total_unknown
        print(summary + " --")

    if args.dry_run and len([c for c in args.creator.split(",") if c.strip()]) > 1:
        total_line = f"\n== Total estimated download size: {human_size(grand_total_bytes)} =="
        if grand_total_unknown:
            total_line += f" ({grand_total_unknown} file(s) of unknown size not included)"
        print(total_line)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Re-run the same command to resume.", file=sys.stderr)
        sys.exit(130)
