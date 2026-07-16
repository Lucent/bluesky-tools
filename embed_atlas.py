#!/usr/bin/env python3
"""Turn an unpacked Bluesky archive into JSONL for Nomic Atlas semantic search --
one line per post, annotated with thread_id / parent_id / depth so Atlas can facet
whole threads. Record parsing is shared with the other tools (thread_graph)."""

import json
import sys

from thread_graph import parent_rkey, read_posts


def annotate(posts):
	by_rkey = {p["rkey"]: p for p in posts}

	def root_and_depth(post):
		depth = 0
		while (parent := parent_rkey(post)) and parent in by_rkey:
			post = by_rkey[parent]
			depth += 1
		return post["rkey"], depth

	for p in posts:
		p["thread_id"], p["depth"] = root_and_depth(p)


def main():
	posts = read_posts(sys.argv[1])
	annotate(posts)
	for p in posts:
		print(json.dumps({
			"id": p["rkey"],
			"text": p["text"],
			"created_at": p["createdAt"],
			"thread_id": p["thread_id"],
			"parent_id": parent_rkey(p),
			"depth": p["depth"],
		}, ensure_ascii=False))


if __name__ == "__main__":
	main()
