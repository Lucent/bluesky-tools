# Process account JSON export from https://observablehq.com/@aendra/bluesky-backup-tool

import json
import sys

def read_json(filename):
	with open(filename, 'r') as file:
		return json.load(file)

def transform_text_to_markdown(text, facets):
	for facet in reversed(facets):
		if facet['features'][0]['$type'] == "app.bsky.richtext.facet#mention":
			continue
		start = facet['index']['byteStart']
		end = facet['index']['byteEnd']
		link = facet['features'][0]['uri']
		link_text = text[start:end]
		markdown_link = f"[{link_text}]({link})"
		text = text[:start] + markdown_link + text[end:]
	return text

def process_posts(posts):
	posts_by_cid = {post['cid']: post for post in posts}

	for post in posts:
		post['replies'] = []
		if 'facets' in post:
			post['text'] = transform_text_to_markdown(post['text'], post['facets'])

		if 'embed' in post and post['embed']['$type'] == "app.bsky.embed.images":
			images_text = '\n'.join([f"[{image['alt']}]" for image in post['embed']['images']])
			post['text'] += f"\n{images_text}"

		if 'embed' in post and post['embed']['$type'] == "app.bsky.embed.external":
			embed = post['embed']['external']
			post['text'] += f"\n[{embed['title']}]({embed['uri']})"

		if 'embed' in post and post['embed']['$type'] == "app.bsky.embed.record":
			quoted_cid = post['embed']['record']['cid']
			if quoted_cid in posts_by_cid:
				quoted_post = posts_by_cid[quoted_cid]
				date = quoted_post['createdAt'].split('T')[0]
				quote_text = quoted_post['text'].replace('\n', '\n > ')
				post['text'] += f"\n > {quote_text} —{date}"

	for post in posts:
		if 'reply' in post and 'parent' in post['reply']:
			parent_cid = post['reply']['parent']['cid']
			if parent_cid in posts_by_cid:
				posts_by_cid[parent_cid]['replies'].append(post)

	root_posts = [post for post in posts if 'reply' not in post or 'parent' not in post['reply']]
	return root_posts

def print_posts(posts):
	last_root_date = [None]  # Tracks the date of the last root post

	def print_date_if_new(date):
		# Print the date only if it's different from the last root post's date
		if date != last_root_date[0]:
			print("\n--" + date + "--")
			last_root_date[0] = date

	def print_post(post, depth=0):
		date = post['createdAt'].split('T')[0]
		indent = ' ↳ ' * depth  # Adjust indent for replies

		if depth == 0:  # It's a root post
			print_date_if_new(date)
		print(f"{indent}{post['text']}", end="")
		if depth != 0:
			print(f" —{date}", end="")
		print("\n")

		for reply in post['replies']:
			print_post(reply, depth + 1)

	for post in posts:
		print_post(post)

filename = sys.argv[1]
data = read_json(filename)

posts = data['app.bsky.feed.post']

root_posts = process_posts(posts)

print(data['app.bsky.actor.profile'][0]['displayName'] + "\n")
print(data['app.bsky.actor.profile'][0]['description'] + "\n")

print_posts(root_posts)
