# Floatplane back-catalogue downloader

A small command-line tool that downloads all (or a date-filtered subset of)
video posts from a Floatplane creator you're subscribed to — e.g. Linus Tech
Tips — for personal offline archival. It talks to Floatplane's own (public,
reverse-engineered) API, so no browser automation or captcha-solving is
involved.

This is for personal use with your own paid subscription. Don't use it to
redistribute content — that would violate Floatplane's and LMG's terms of
service and copyright.

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`
- An active Floatplane subscription that covers the creator(s) you want

## Authentication

The recommended method is to give the script your session cookie, since it
avoids Floatplane's browser captcha entirely and never touches your
password:

1. Log into <https://www.floatplane.com> in your normal browser.
2. Open dev tools → Application/Storage → Cookies → `https://www.floatplane.com`.
3. Copy the value of the `sails.sid` cookie.
4. Pass it via `--cookie <value>` or set the `FLOATPLANE_SID` environment
   variable (preferred, keeps it out of shell history).

This cookie expires after a while — if the script reports it's no longer
authenticated, just grab a fresh one the same way.

Alternatively you can pass `--username`/`--password` (or `FLOATPLANE_USER`/
`FLOATPLANE_PASS`), and the script will log in directly and prompt for a 2FA
code if your account has it enabled. If Floatplane responds asking for a
captcha (which happens for some accounts/IPs), fall back to `--cookie`.

## Usage

```bash
pip install -r requirements.txt

# Everything LTT has ever posted, into ./floatplane-downloads
FLOATPLANE_SID="<cookie value>" python3 floatplane_dl.py

# A specific quality, custom output folder
FLOATPLANE_SID="..." python3 floatplane_dl.py --quality 1080p --output /media/LTT

# Cap bandwidth at 2 MB/s so it can just run in the background for days
FLOATPLANE_SID="..." python3 floatplane_dl.py --limit-rate 2M

# Multiple LMG creators in one run
FLOATPLANE_SID="..." python3 floatplane_dl.py --creator linustechtips,techlinked,techquickie

# Just the Floatplane Exclusive sub-channel of LTT (not a separate creator - see note below)
FLOATPLANE_SID="..." python3 floatplane_dl.py --channel fpexclusive

# Only content from 2024 onward
FLOATPLANE_SID="..." python3 floatplane_dl.py --from-date 2024-01-01

# See what would be downloaded without actually downloading anything
FLOATPLANE_SID="..." python3 floatplane_dl.py --dry-run
```

Run `python3 floatplane_dl.py --help` for all options.

### Creators vs. sub-channels

`--creator` selects between separate LMG accounts on Floatplane (linustechtips,
techlinked, techquickie, ...). "Floatplane Exclusive" is *not* one of these -
it's a sub-channel that lives under the `linustechtips` creator itself, the
same way "Main", "Behind the Scenes", and "Livestreams" do. Passing
`--creator fpexclusive` will fail with a "Creator not found" error because
Floatplane doesn't have a creator by that name.

To get just that content, use `--channel` instead, which filters posts by
sub-channel `urlname` within whichever creator(s) `--creator` selects
(default: `linustechtips`):

```bash
FLOATPLANE_SID="..." python3 floatplane_dl.py --channel fpexclusive
```

If the `urlname` you pass doesn't match any sub-channel on that creator, the
script prints the sub-channels it does know about so you can pick the right
one.

## Behaviour

- Videos are saved as `<output>/<Creator Name>/<date> - <title> [<id>].mp4`.
- If a file already exists at that path, it's skipped — safe to re-run
  periodically to pick up new uploads or resume an interrupted run.
- A partial download resumes via HTTP `Range` requests rather than
  restarting from scratch.
- Floatplane's CDN quality labels vary by video (e.g. `360p` up to `4K`);
  `--quality` matches a label exactly and falls back to the highest
  available quality if that label doesn't exist for a given video, with a
  warning.
- Requests are retried automatically if Floatplane responds with `429 Too
  Many Requests`, honouring its `Retry-After` header.
- `--limit-rate` caps average download bandwidth (per file, not aggregate),
  e.g. `--limit-rate 500K`, `--limit-rate 2M`, `--limit-rate 1.5G`. Handy
  for a slow, unattended run that shouldn't compete with everything else
  on your connection.
- `--dry-run` prints the size of each video (from Floatplane's own metadata,
  at whatever `--quality` would be picked) plus a per-creator and overall
  total, so you can check free disk space before committing to a big
  back-catalogue run. This is the total for *this run* — files already
  present in `--output` are skipped and not counted, so re-running after a
  partial download only estimates what's left. A file occasionally has no
  size in Floatplane's metadata; those are called out separately rather
  than silently under-counting the total. Because this needs Floatplane's
  per-video delivery info to get a size, `--dry-run` makes the same number
  of API calls as a real run — it just skips the actual video download.
- Floatplane throttles that per-video delivery-info lookup much harder than
  its other endpoints when it's hit back-to-back with no download in
  between, which a `--dry-run` size scan does by nature. To cope: calls are
  paced a couple of seconds apart, and if Floatplane still asks for a wait
  longer than 20s, size lookups are dropped for the rest of that dry run
  (remaining files just list as "size unknown" instead of the whole run
  stalling for however long Floatplane asked for). This doesn't apply to a
  real download run, where the download itself already spaces requests out.

## Known limitations

- Only downloads video posts. Text-only or audio-only (podcast) posts are
  skipped.
- No parallel downloads — this is intentionally conservative to stay well
  clear of rate limits on a big back-catalogue run (LTT's catalogue is
  thousands of videos; expect this to take a long time and a lot of disk
  space).
- Built against Floatplane's community-documented API
  (github.com/jamamp/FloatplaneAPI). Floatplane can change this without
  notice, which would break the script.
