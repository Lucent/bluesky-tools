#!/usr/bin/env python3
"""Threaded plain-text export of a Bluesky archive: chronological, quotes inlined,
solo quoted posts deduped -- the shape that reads best when fed to an LLM.
Record parsing is shared with the other tools (thread_graph)."""

import json
import os
import re
import sys

from thread_graph import parent_rkey, quoted_rkeys, read_posts

POST_LINK = re.compile(r"/post/([0-9a-z]+)")


def markdown_text(text, facets):
	"""Inline link facets as [text](uri). Facet offsets are BYTE offsets into the
	UTF-8 encoding, so slice the encoded bytes, never the str."""
	b = text.encode()
	out, cursor = [], 0
	for facet in sorted(facets or [], key=lambda f: f["index"]["byteStart"]):
		feature = facet["features"][0]
		if feature["$type"] != "app.bsky.richtext.facet#link":
			continue
		start, end = facet["index"]["byteStart"], facet["index"]["byteEnd"]
		if start < cursor:
			continue
		out.append(b[cursor:start].decode())
		out.append(f"[{b[start:end].decode()}]({feature['uri']})")
		cursor = end
	out.append(b[cursor:].decode())
	return "".join(out)


def media_lines(post):
	"""Text stand-ins for embedded media: the author's alt text when there is one, a
	bare placeholder when there isn't (never an empty '[]')."""
	embed = post.get("embed") or {}
	media = embed.get("media", {}) if embed.get("$type") == "app.bsky.embed.recordWithMedia" else embed
	kind = media.get("$type")
	if kind == "app.bsky.embed.images":
		return [f"[{img.get('alt') or 'image'}]" for img in media.get("images", [])]
	if kind == "app.bsky.embed.external":
		ext = media.get("external", {})
		return [f"[{ext.get('title') or 'link'}]({ext.get('uri', '')})"]
	if kind == "app.bsky.embed.video":
		return [f"[{media.get('alt') or 'video'}]"]
	return []


def quote_keys(post):
	"""Every rkey this post quotes: embed quotes plus facet links to a post URL --
	the same facet-promotion rule the browser applies at intake."""
	keys = list(quoted_rkeys(post))
	for facet in post.get("facets") or []:
		for feature in facet.get("features", []):
			if feature.get("$type") == "app.bsky.richtext.facet#link":
				m = POST_LINK.search(feature.get("uri", ""))
				if m:
					keys.append(m.group(1))
	return keys


def process_posts(posts):
	"""Wire the reply forest and inline quotes; return the chronological root stream."""
	by_rkey = {p["rkey"]: p for p in posts}

	# Render every post's text first, so a quote block always inlines finished markdown.
	for post in posts:
		post["has_words"] = bool(post["text"].strip())
		post["text"] = "\n".join([markdown_text(post["text"], post.get("facets"))] + media_lines(post)).strip("\n")
		post["replies"] = []
		post["quoted"] = []

	for post in posts:
		parent = parent_rkey(post)
		if parent and parent in by_rkey:
			by_rkey[parent]["replies"].append(post)
		elif parent:
			post["external_reply"] = True
		for key in dict.fromkeys(quote_keys(post)):
			if key in by_rkey and key != post["rkey"]:
				post["quoted"].append(by_rkey[key])

	# A wordless reply into someone else's thread gives a text reader nothing (its
	# payload is a bare image or a quote connector); drop it unless our own replies
	# hang off it. Quotes are then counted over the survivors, so a post quoted only
	# by a dropped connector still surfaces as its own root.
	survivors = [p for p in posts if p["has_words"] or not p.get("external_reply") or p["replies"]]
	quoted_anywhere = {q["rkey"] for p in survivors for q in p["quoted"]}

	# Roots, chronological: not a reply to a held post, minus solo posts whose whole
	# text already appears inline wherever they are quoted (the dedup).
	return [
		p for p in survivors
		if not ((parent := parent_rkey(p)) and parent in by_rkey)
		and not (p["rkey"] in quoted_anywhere and not p["replies"])
	]


def print_posts(roots):
	last_date = None

	def print_post(post, depth):
		nonlocal last_date
		date = post["createdAt"].split("T")[0]
		print()
		if depth == 0:
			print()
			if date != last_date:
				print()
				print("## " + date)
				last_date = date
		# A reply into someone else's thread stands alone with an explicit marker --
		# never drawn as a child of the unrelated post that precedes it.
		lead = "↳ elsewhere: " if post.get("external_reply") else " ↳ " * depth
		print(f"{lead}{post['text']}", end="")
		if depth:
			print(f" —{date}", end="")
		for q in post["quoted"]:
			for line in q["text"].split("\n"):
				print(f"\n{'   ' * depth}> {line}", end="")
			print(f" —{q['createdAt'].split('T')[0]}", end="")
		for reply in post["replies"]:
			print_post(reply, depth + 1)

	for post in roots:
		print_post(post, 0)


def main():
	directory = sys.argv[1]
	limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
	posts = read_posts(directory)
	if limit:
		posts = posts[-limit:]
	roots = process_posts(posts)

	with open(os.path.join(directory, "app.bsky.actor.profile", "self.json"), encoding="utf-8") as fh:
		profile = json.load(fh)
	print(profile["displayName"])
	print()
	print(profile["description"])
	print_posts(roots)


if __name__ == "__main__":
	main()
