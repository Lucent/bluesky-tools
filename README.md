# Bluesky Tools

Utilities for downloading and exploring Bluesky accounts via goat.

## Usage

Required packages: jq, golang

- python3 -m venv .venv
- source .venv/bin/activate
- pip install -r requirements.txt

- `./install.sh`
  Installs the [goat](https://github.com/bluesky-social/indigo/blob/main/cmd/goat/README.md) repo-fetching tool.

- `./fetch.sh username.bsky.social`
  Fetches the given account's `.car` archive, then:
  - Produces a **threaded plain-text** chronological export
  - Outputs a `.jsonl` file for loading into [Nomic Atlas](https://atlas.nomic.ai)
  - Generates a **heatmap** of post activity

- `python thread_graph.py did:plc:... 3jtc66csqyr2o > post.mmd`
  Emits a Mermaid flowchart for the entire thread containing that post (ancestors + every reply branch), shows every post that quotes it, and follows any quoted posts (recursively) to include their own replies/quotes. Render the `.mmd` text with [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) or another viewer to produce an SVG.

## Thread browser (`browse.html`)

An interactive, pan/zoom tree view of an account's threads. It finds the root of
each reply and draws the whole reply tree, lays quotes and quoted-by posts in
gutters beside each box, and **fetches the outside posts you replied to live from
the public API** (no login) so you see the conversation, not just your half.
Search matches text, image alt, and link URLs; ⌘/ctrl-click a quote to merge its
thread in or pull a satellite into the tree. It reads a local archive and shows no
likes, metrics, or ranking. Layout uses the vendored
[d3-flextree](https://github.com/Klortho/d3-flextree) (`flextree.js`).

First get an archive directory with `./install.sh` then `./fetch.sh you.bsky.social`
(above) — that produces the `did:plc:…` record folder the browser reads.

### Run locally (no Docker)

```
python3 thread_browser.py did:plc:xxxxxxxx --serve 8000
```

Builds `index.json` from the archive and serves this folder; open
<http://localhost:8000/browse.html>. Pure stdlib (no `pip install`). Needs
internet: it pulls the posts you replied to and the images from the public Bluesky
API/CDN at view time.

### Serve publicly (Docker + Cloudflare Tunnel)

```
cp .env.example .env          # set ARCHIVE_DID=did:plc:xxxxxxxx (the folder name)
                              # and TUNNEL_TOKEN=... (tunnel -> http://thread-browser:8000)
docker compose up -d
```

The container rebuilds `index.json` on start from the read-only repo mount and
serves `browse.html` (plus the experimental `layout-lab.html`). Nothing is written
back to the host, and `ARCHIVE_DID` is the only per-account configuration.
