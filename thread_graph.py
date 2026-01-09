#!/usr/bin/env python3
"""Render a reply/quote network for a Bluesky post as a Mermaid diagram."""

import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


def read_posts(directory: str) -> List[dict]:
    post_dir = os.path.join(directory, "app.bsky.feed.post")
    if not os.path.isdir(post_dir):
        raise FileNotFoundError(f"Could not find app.bsky.feed.post under {directory}")

    posts: List[dict] = []
    for root, _dirs, files in os.walk(post_dir):
        for filename in files:
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(root, filename)
            with open(filepath, "r", encoding="utf-8") as handle:
                post = json.load(handle)
            post["rkey"] = os.path.splitext(filename)[0]
            posts.append(post)

    posts.sort(key=lambda item: item.get("createdAt", ""))
    return posts


def parent_rkey(post: dict) -> Optional[str]:
    reply = post.get("reply")
    if not reply:
        return None
    parent = reply.get("parent")
    if not parent:
        return None
    uri = parent.get("uri")
    if not uri:
        return None
    return uri.rsplit("/", maxsplit=1)[-1]


def quoted_rkeys(post: dict) -> List[str]:
    embed = post.get("embed")
    if not embed:
        return []

    embed_type = embed.get("$type")
    if embed_type == "app.bsky.embed.record":
        record = embed.get("record", {})
        uri = record.get("uri")
        return [uri.rsplit("/", maxsplit=1)[-1]] if uri else []

    if embed_type == "app.bsky.embed.recordWithMedia":
        record = embed.get("record", {})
        inner = record.get("record", {})
        uri = inner.get("uri")
        return [uri.rsplit("/", maxsplit=1)[-1]] if uri else []

    return []


def sanitize_label(text: str) -> str:
    return (
        text.replace("\\", " ")
        .replace("\n", "<br/>")
        .replace("[", "(")
        .replace("]", ")")
        .replace("\"", "'")
    )


def node_label(post: dict) -> str:
    date = post.get("createdAt", "")[:10]
    snippet = post.get("text", "").strip()
    if date:
        label = f"{date}<br/>{snippet}"
    else:
        label = snippet or "(no text)"
    return sanitize_label(label or "(no text)")


def find_thread_root(post: dict, posts_by_rkey: Dict[str, dict]) -> Tuple[dict, List[dict]]:
    ancestors: List[dict] = []
    current = post
    seen: set[str] = set()

    while True:
        parent_key = parent_rkey(current)
        if not parent_key or parent_key in seen:
            break
        seen.add(parent_key)
        parent = posts_by_rkey.get(parent_key)
        if not parent:
            break
        ancestors.append(parent)
        current = parent

    ancestors.reverse()
    return current, ancestors


def build_relationships(posts: List[dict]):
    replies_by_parent: Dict[str, List[dict]] = defaultdict(list)
    quotes_by_target: Dict[str, List[dict]] = defaultdict(list)
    quotes_from_post: Dict[str, List[dict]] = defaultdict(list)

    posts_by_rkey = {post["rkey"]: post for post in posts}

    for post in posts:
        parent = parent_rkey(post)
        if parent and parent in posts_by_rkey:
            replies_by_parent[parent].append(post)

        for quoted in quoted_rkeys(post):
            if quoted in posts_by_rkey:
                quotes_by_target[quoted].append(post)
                quotes_from_post[post["rkey"]].append(posts_by_rkey[quoted])

    # Ensure deterministic ordering
    for items in replies_by_parent.values():
        items.sort(key=lambda item: item.get("createdAt", ""))
    for items in quotes_by_target.values():
        items.sort(key=lambda item: item.get("createdAt", ""))
    for items in quotes_from_post.values():
        items.sort(key=lambda item: item.get("createdAt", ""))

    return replies_by_parent, quotes_by_target, quotes_from_post


def render_mermaid(
    target: dict,
    posts_by_rkey: Dict[str, dict],
    replies_by_parent: Dict[str, List[dict]],
    quotes_by_target: Dict[str, List[dict]],
    quotes_from_post: Dict[str, List[dict]],
) -> str:
    lines: List[str] = ["flowchart TB"]
    node_ids: Dict[str, str] = {}
    expanded: set[str] = set()

    def ensure_node(post: dict) -> str:
        rkey = post["rkey"]
        if rkey not in node_ids:
            node_id = f"n{len(node_ids)}"
            node_ids[rkey] = node_id
            label = node_label(post)
            lines.append(f'  {node_id}["{label}"]')
        return node_ids[rkey]

    def expand(rkey: str) -> None:
        if rkey in expanded:
            return
        expanded.add(rkey)

        post = posts_by_rkey.get(rkey)
        if not post:
            return

        parent_id = ensure_node(post)

        for reply in replies_by_parent.get(rkey, []):
            child_id = ensure_node(reply)
            lines.append(f"  {parent_id} --> {child_id}")
            expand(reply["rkey"])

        for quoted_post in quotes_from_post.get(rkey, []):
            quoted_id = ensure_node(quoted_post)
            lines.append(f'  {parent_id} -. "quotes" .-> {quoted_id}')
            expand(quoted_post["rkey"])

    root_post, _ = find_thread_root(target, posts_by_rkey)
    expand(root_post["rkey"])

    for quoting_post in quotes_by_target.get(target["rkey"], []):
        expand(quoting_post["rkey"])

    target_id = ensure_node(target)
    lines.append("  classDef target fill:#fff4ce,stroke:#f4a127,stroke-width:2px;")
    lines.append(f"  class {target_id} target")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a Mermaid flowchart capturing replies and quotes for a post.",
    )
    parser.add_argument(
        "directory",
        help="Path to the DID folder that contains app.bsky.feed.post",
    )
    parser.add_argument(
        "rkey",
        help="Record key of the post to visualize (e.g. 3jtc66csqyr2o).",
    )
    parser.add_argument(
        "--output",
        help="Optional file path to write the Mermaid diagram instead of stdout.",
    )
    args = parser.parse_args()

    posts = read_posts(args.directory)
    posts_by_rkey = {post["rkey"]: post for post in posts}

    target = posts_by_rkey.get(args.rkey)
    if not target:
        raise SystemExit(f"Could not find post with rkey {args.rkey}")

    replies_by_parent, quotes_by_target, quotes_from_post = build_relationships(posts)
    mermaid = render_mermaid(
        target,
        posts_by_rkey,
        replies_by_parent,
        quotes_by_target,
        quotes_from_post,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(mermaid)
    else:
        print(mermaid)


if __name__ == "__main__":
    main()
