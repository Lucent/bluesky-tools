#!/usr/bin/env python3
"""Build a compact index.json for browse.html and (optionally) serve it.

Reuses thread_graph.py for parsing and relationship walking so the browser stays
in lockstep with the other tools.
"""

import argparse
import glob
import http.server
import json
import os
import re
import socketserver
import sys
import urllib.parse

from thread_graph import parent_rkey, quoted_rkeys, read_posts

# A faceted link like https://bsky.app/profile/<actor>/post/<rkey> targets a
# post, not a web page. The <actor> may be a stale handle, but the rkey still
# identifies the record, so we match on rkey alone.
_POST_LINK = re.compile(r"/post/([0-9a-z]+)")
_X_HOSTS = {"twitter.com", "x.com", "mobile.twitter.com"}
# Tweet card titles look like:  Display Name on X: "the tweet text"
_TWEET_TITLE = re.compile(r'^(.*?) on (?:X|Twitter):\s*"?(.*?)"?\s*$', re.S)


def link_post_rkey(uri, known_rkeys):
    """Return the rkey a facet link points at, if it names a post we have."""
    match = _POST_LINK.search(uri or "")
    if match and match.group(1) in known_rkeys:
        return match.group(1)
    return None


def is_x_host(uri):
    """True if the URI points at Twitter / X."""
    try:
        host = urllib.parse.urlparse(uri).netloc.lower()
    except ValueError:
        return False
    return host[4:] in _X_HOSTS if host.startswith("www.") else host in _X_HOSTS


def tweet_node(ext, uri):
    """Build a synthetic graph node for a quoted Twitter/X post, so the browser
    can treat it as a normal quote target instead of a special case."""
    title = (ext.get("title") or "").strip()
    text = (ext.get("description") or "").strip()
    author = ""
    match = _TWEET_TITLE.match(title)
    if match:
        author = match.group(1).strip()
        text = text or match.group(2).strip()
    if not author:
        handle = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)", uri)
        if handle and handle.group(1).lower() not in ("i", "intent", "home"):
            author = "@" + handle.group(1)
    text = text or title or (author + " on X" if author else "X post")
    node = {"tweet": True, "u": uri, "t": text}
    if author:
        node["a"] = author
    return node


def detect_handle(script_dir):
    """Best-effort handle: the toolchain writes <handle>.jsonl / <handle>.txt
    next to this script, so a unique domain-like stem there is the handle."""
    for pattern in ("*.jsonl", "*.txt"):
        cands = set()
        for path in glob.glob(os.path.join(script_dir, pattern)):
            stem = os.path.basename(path).rsplit(".", 1)[0]
            if "." in stem and not stem.startswith("did:"):
                cands.add(stem)
        if len(cands) == 1:
            return next(iter(cands))
    return ""


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


def build_index(posts):
    """Return a compact dict[rkey] -> entry suitable for the JS browser.

    Keys are short to keep the wire size down on big archives:
      t   text
      d   createdAt
      p   parent rkey (if any reply)
      q   list of quoted rkeys (embed quotes + faceted post-links + tweet nodes)
      f   raw facets; post-links and tweet-links are stripped

    Quoted tweets become synthetic nodes keyed "x:<rkey>" with {tweet, u, t, a}
    so the browser treats them like any other quote target.
      img number of attached images
      alt image alt strings (skipped if all empty)
      ext {"u": uri, "t": title, "d": description} for external embed cards
      vid true if the embed is a video
    """
    known_rkeys = {p["rkey"] for p in posts}
    index = {}
    tweet_nodes = {}                       # synthetic "x:<rkey>" nodes for quoted tweets
    for post in posts:
        entry = {
            "t": post.get("text", ""),
            "d": post.get("createdAt", ""),
        }
        par = parent_rkey(post)
        if par:
            entry["p"] = par
        quotes = list(quoted_rkeys(post))

        # Walk facets: a link to one of our posts is really a quote; a link to
        # a tweet is stripped (rendered as plain text); other links are kept.
        kept_facets = []
        for facet in post.get("facets") or []:
            linked = None
            x_link = False
            for feat in facet.get("features", []):
                if feat.get("$type") == "app.bsky.richtext.facet#link":
                    uri = feat.get("uri", "")
                    linked = link_post_rkey(uri, known_rkeys)
                    x_link = x_link or is_x_host(uri)
            if linked:
                if linked not in quotes:
                    quotes.append(linked)
            elif not x_link:
                kept_facets.append(facet)

        if kept_facets:
            entry["f"] = kept_facets

        embed = post.get("embed") or {}
        kind = embed.get("$type")
        media = embed
        if kind == "app.bsky.embed.recordWithMedia":
            media = embed.get("media") or {}
            kind = media.get("$type")

        if kind == "app.bsky.embed.images":
            imgs = media.get("images", [])
            entry["img"] = len(imgs)
            alts = [img.get("alt", "") for img in imgs]
            if any(alts):
                entry["alt"] = alts
        elif kind == "app.bsky.embed.external":
            ext = media.get("external", {})
            uri = ext.get("uri", "")
            if is_x_host(uri):
                # A quoted tweet becomes a real node the graph can point at.
                tid = "x:" + post["rkey"]
                tweet_nodes[tid] = tweet_node(ext, uri)
                quotes.append(tid)
            else:
                card = {"u": uri, "t": ext.get("title", "")}
                if ext.get("description"):
                    card["d"] = ext["description"]
                entry["ext"] = card
        elif kind == "app.bsky.embed.video":
            entry["vid"] = True

        if quotes:
            entry["q"] = quotes

        index[post["rkey"]] = entry
    index.update(tweet_nodes)
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

    index = build_index(posts)
    # The DID folder is named after the DID; the browser uses it to link each
    # post to its real bsky.app permalink.
    did = os.path.basename(os.path.normpath(args.directory))
    if not did.startswith("did:"):
        did = ""
    meta = read_profile(args.directory)
    handle = detect_handle(script_dir)
    if handle:
        meta["handle"] = handle
    payload = {"did": did, "meta": meta, "posts": index}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
    who = meta.get("handle") or meta.get("name") or "?"
    print(f"Wrote {out_path} ({len(index)} entries, {who})", file=sys.stderr)

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
