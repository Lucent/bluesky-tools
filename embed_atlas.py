#!/usr/bin/env python3
"""
goat_bluesky_to_atlas.py  ──  turn a Bluesky repo dump (GOAT export)
into a JSONL ready for Nomic Atlas semantic search + thread filters
"""
import json, os, sys
from collections import defaultdict

# ---------- helpers reused from your existing script ----------
def read_json(fp):
	with open(fp, "r") as f:
		return json.load(f)

def walk_posts(repo_dir):
	post_dir = os.path.join(repo_dir, "app.bsky.feed.post")
	for root, _, files in os.walk(post_dir):
		for fname in files:
			post = read_json(os.path.join(root, fname))
			post["rkey"] = os.path.splitext(fname)[0]
			yield post

# ---------- build parent / child graph ----------
def index_by_rkey(posts):
	return {p["rkey"]: p for p in posts}

def attach_children(posts, idx):
	# reuse the same reply-link logic you already tested
	for p in posts:
		p["children"] = []
	for p in posts:
		if "reply" in p and "parent" in p["reply"]:
			parent_rkey = p["reply"]["parent"]["uri"].split("/")[-1]
			if parent_rkey in idx:						# internal reply
				idx[parent_rkey]["children"].append(p)	# :contentReference[oaicite:3]{index=3}
	return posts

# ---------- derive thread_id, parent_id, depth ----------
def annotate_threads(posts, idx):
	def root_and_depth(post):
		depth = 0
		cur = post
		while "reply" in cur and "parent" in cur["reply"]:
			parent_rkey = cur["reply"]["parent"]["uri"].split("/")[-1]
			if parent_rkey not in idx:			# replied to someone outside dump
				break
			cur = idx[parent_rkey]
			depth += 1
		return cur["rkey"], depth

	for p in posts:
		thread_id, depth = root_and_depth(p)
		parent_id = (
			p["reply"]["parent"]["uri"].split("/")[-1]
			if "reply" in p and "parent" in p["reply"] else None
		)
		p["thread_id"] = thread_id
		p["parent_id"] = parent_id
		p["depth"] = depth
	return posts

# ---------- emit JSON-lines ----------
def write_jsonl(posts):
	for p in posts:
		print(json.dumps({
			"id": p["rkey"],
			"text": p["text"],
			"created_at": p["createdAt"],
			"thread_id": p["thread_id"],
			"parent_id": p["parent_id"],
			"depth": p["depth"],
		}, ensure_ascii=False))

if __name__ == "__main__":
	repo_root = sys.argv[1]			  # path to repo export dir
	posts = list(walk_posts(repo_root))
	idx = index_by_rkey(posts)
	attach_children(posts, idx)
	annotate_threads(posts, idx)
	write_jsonl(posts)
