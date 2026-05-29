#!/usr/bin/env python3
"""Build a compact index.json for browse.html and (optionally) serve it.

Reuses thread_graph.py for parsing and relationship walking so the browser stays
in lockstep with the other tools.
"""

import argparse
import http.server
import json
import os
import re
import socketserver
import sys
import urllib.parse

from thread_graph import parent_rkey, quoted_rkeys, read_posts

# CDN templates: the build pre-resolves every blob CID into the same URL shape the
# AppView returns at runtime, so archive entries land in the browser already shaped
# like API-view posts (no per-load CID→URL fix-up).
_CDN_FULLSIZE = "https://cdn.bsky.app/img/feed_fullsize/plain/"
_CDN_THUMBNAIL = "https://cdn.bsky.app/img/feed_thumbnail/plain/"
_VIDEO_BASE = "https://video.bsky.app/watch/"


def read_profile(directory):
    """Pull display name / description / avatar from the actor profile record."""
    path = os.path.join(directory, "app.bsky.actor.profile", "self.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        prof = json.load(fh)
    meta = {"name": prof.get("displayName", ""), "desc": prof.get("description", "")}
    avatar = (prof.get("avatar") or {}).get("ref", {}).get("$link")
    if avatar:
        meta["avatar"] = avatar
    return meta


def parent_uri(post):
    """Full AT-URI of the post this one replies to, or None."""
    reply = post.get("reply") or {}
    parent = reply.get("parent") or {}
    return parent.get("uri") or None


def build_index(posts, repo_did=""):
    """Return a compact dict[rkey] -> entry suitable for the JS browser.

    Keys are short to keep the wire size down on big archives:
      t   text
      d   createdAt
      p   parent rkey (if any reply)
      xp  parent author DID, only when the reply targets someone *else's* post
          (so the browser can fetch that one post from the public API on demand
          and show it as the thread's external root)
      xr  thread root rkey, set alongside xp — lets the browser group every one
          of our posts that share an external thread onto a single graph
      xrd thread root author DID, when the root isn't ours (so the root post can
          be fetched too)
      q   list of embed-quoted rkeys; the browser promotes facet post-links and
          X-host cards to quotes at intake (same rule applied to network posts)
      f   raw facets, exactly as the record carries them
      img list of {u: full CDN URL, a?: alt, ar?: [w, h]} — API-view shape
      ext {u, t, d?, thumb?: full CDN URL} for external embed cards
      vid {a?, ar?} sibling-by playlist and poster URLs at the entry level
    """
    video_did = urllib.parse.quote(repo_did, safe="")    # video.bsky.app insists on a percent-encoded DID
    known_rkeys = {p["rkey"] for p in posts}
    index = {}
    for post in posts:
        entry = {
            "t": post.get("text", ""),
            "d": post.get("createdAt", ""),
        }
        par = parent_rkey(post)
        if par:
            entry["p"] = par
            # A reply whose parent we don't hold is either a deleted own post or,
            # if the parent's DID isn't ours, someone else's post. Flag the latter
            # with its author DID so the browser can pull that one post on demand.
            if par not in known_rkeys:
                puri = parent_uri(post) or ""
                pdid = puri.split("/")[2] if puri.startswith("at://") else ""
                if pdid and pdid != repo_did:
                    entry["xp"] = pdid
                # Record the thread root too, so the browser can group all of our
                # posts in the same outside thread onto one graph.
                ruri = ((post.get("reply") or {}).get("root") or {}).get("uri") or ""
                if ruri.startswith("at://"):
                    rparts = ruri.split("/")
                    entry["xr"] = rparts[-1]
                    if rparts[2] != repo_did:
                        entry["xrd"] = rparts[2]
        quotes = list(quoted_rkeys(post))

        # Facets pass through raw — the browser promotes post-link facets to quotes
        # and strips X-host links at intake, so the rule lives in one place.
        if post.get("facets"):
            entry["f"] = post["facets"]

        embed = post.get("embed") or {}
        kind = embed.get("$type")
        media = embed
        if kind == "app.bsky.embed.recordWithMedia":
            media = embed.get("media") or {}
            kind = media.get("$type")

        if kind == "app.bsky.embed.images":
            images = []
            for img in media.get("images", []):
                cid = (((img.get("image") or {}).get("ref") or {}).get("$link"))
                if not cid:
                    continue
                rec = {"u": f"{_CDN_FULLSIZE}{repo_did}/{cid}@jpeg"}
                if img.get("alt"):
                    rec["a"] = img["alt"]
                ar = img.get("aspectRatio") or {}
                if ar.get("width") and ar.get("height"):
                    rec["ar"] = [ar["width"], ar["height"]]   # size the box to the image
                images.append(rec)
            if images:
                entry["img"] = images
        elif kind == "app.bsky.embed.external":
            # Always emit the raw card; the browser promotes X-host cards to synthetic
            # tweet-quote nodes at intake (same rule applied to network posts too).
            ext = media.get("external", {})
            card = {"u": ext.get("uri", ""), "t": ext.get("title", "")}
            if ext.get("description"):
                card["d"] = ext["description"]
            thumb = ext.get("thumb") or {}
            cid = (thumb.get("ref") or {}).get("$link") or thumb.get("cid")
            if cid:
                card["thumb"] = f"{_CDN_THUMBNAIL}{repo_did}/{cid}@jpeg"
            entry["ext"] = card
        elif kind == "app.bsky.embed.video":
            cid = (((media.get("video") or {}).get("ref") or {}).get("$link"))
            rec = {}
            ar = media.get("aspectRatio") or {}
            if ar.get("width") and ar.get("height"):
                rec["ar"] = [ar["width"], ar["height"]]
            if media.get("alt"):
                rec["a"] = media["alt"]
            if cid:
                base = f"{_VIDEO_BASE}{video_did}/{cid}/"
                entry["playlist"] = base + "playlist.m3u8"
                entry["poster"] = base + "thumbnail.jpg"
                entry["vid"] = rec
            elif rec:
                entry["vid"] = rec

        if quotes:
            entry["q"] = quotes

        index[post["rkey"]] = entry
    return index


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "directory",
        help="Path to the DID folder (the one containing app.bsky.feed.post/).",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Where to write the index. Defaults to <directory>/index.json so the "
             "file is served right next to browse.html.",
    )
    ap.add_argument(
        "--serve",
        type=int,
        nargs="?",
        const=8000,
        default=None,
        help="After building, serve browse.html from the script directory at this port "
             "(default 8000).",
    )
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = args.out or os.path.join(script_dir, "index.json")

    posts = read_posts(args.directory)
    print(f"Loaded {len(posts)} posts", file=sys.stderr)

    # The DID folder is named after the DID; the browser uses it to link each
    # post to its real bsky.app permalink, and build_index uses it to tell our
    # own (deleted) parents apart from genuinely external ones.
    did = os.path.basename(os.path.normpath(args.directory))
    if not did.startswith("did:"):
        did = ""

    index = build_index(posts, repo_did=did)
    meta = read_profile(args.directory)
    payload = {"meta": meta, "posts": index}   # the filename encodes the owner DID
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
    print(f"Wrote {out_path} ({len(index)} entries, {meta.get('name') or '?'})", file=sys.stderr)

    if args.serve is not None:
        os.chdir(script_dir)
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", args.serve), handler) as httpd:
            url = f"http://localhost:{args.serve}/browse.html"
            print(f"Serving {script_dir} on {url}", file=sys.stderr)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nStopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
