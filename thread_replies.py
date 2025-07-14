import json
import os
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

def read_posts_from_directory(directory):
	posts = []
	for root, _, files in os.walk(directory):
		for file in files:
			filepath = os.path.join(root, file)
			post = read_json(filepath)
			rkey = os.path.splitext(file)[0]
			post['rkey'] = rkey
			posts.append(post)
	posts.sort(key=lambda x: x['createdAt'])
	return posts

def process_posts(posts):
	posts_by_rkey = {post['rkey']: post for post in posts}

	for post in posts:
		post['replies'] = []
		if 'facets' in post:
			post['text'] = post['text']
			# post['text'] = transform_text_to_markdown(post['text'], post['facets'])

		if 'embed' in post and post['embed']['$type'] == "app.bsky.embed.images":
			images_text = '\n'.join([f"[{image['alt']}]" for image in post['embed']['images']])
			post['text'] += f"\n{images_text}"

		if 'embed' in post and post['embed']['$type'] == "app.bsky.embed.external":
			embed = post['embed']['external']
			post['text'] += f"\n[{embed['title']}]({embed['uri']})"

		if 'embed' in post and post['embed']['$type'] == "app.bsky.embed.record":
			quoted_rkey = post['embed']['record']['uri'].split('/')[-1]
			if quoted_rkey in posts_by_rkey:
				quoted_post = posts_by_rkey[quoted_rkey]
				date = quoted_post['createdAt'].split('T')[0]
				# Store raw quoted text
				post['quotedText'] = quoted_post['text']
				post['quotedDate'] = date

	# Process replies
	for post in posts:
		if 'reply' in post and 'parent' in post['reply']:
			parent_rkey = post['reply']['parent']['uri'].split('/')[-1]
			if parent_rkey in posts_by_rkey:
				posts_by_rkey[parent_rkey]['replies'].append(post)
			else:
				post['external_reply'] = 1

	# Filter out posts that should not appear anywhere
	filtered_posts = []
	for post in posts:
		# Skip external replies that only contain quoted text and no original content
		if (post.get('external_reply') and 'quotedText' in post and not post['text'].strip()):
			continue
		filtered_posts.append(post)

	# Now track quoted posts that actually appear in filtered posts
	quoted_posts = set()
	for post in filtered_posts:
		if 'quotedText' in post:
			quoted_rkey = None
			if 'embed' in post and post['embed']['$type'] == "app.bsky.embed.record":
				quoted_rkey = post['embed']['record']['uri'].split('/')[-1]
				if quoted_rkey in posts_by_rkey:
					quoted_posts.add(quoted_rkey)

	# Root posts are those that aren't replies to internal posts
	# Also exclude posts that are quoted elsewhere but have no replies (to avoid duplication)
	root_posts = [
		post for post in filtered_posts
		if not ('reply' in post and 'parent' in post['reply'] 
			and post['reply']['parent']['uri'].split('/')[-1] in posts_by_rkey)
		and not (post['rkey'] in quoted_posts and len(post['replies']) == 0)
	]
	return root_posts

def print_posts(posts):
	last_root_date = [None]	# Tracks the date of the last root post

	def print_date_if_new(date):
		# Print the date only if it's different from the last root post's date
		if date != last_root_date[0]:
			print()
			print("## " + date)
			last_root_date[0] = date

	def print_post(post, depth=0):
		date = post['createdAt'].split('T')[0]
		indent = ' ↳ ' * depth	# Adjust indent for replies

		print()
		if depth == 0 or post.get('external_reply'):
			print()
		if depth == 0:	# It's a root post
			print_date_if_new(date)
		print(f"{indent}{post['text']}", end="")
		if depth != 0 and not post.get('external_reply'):
			print(f" —{date}", end="")
		if 'quotedText' in post:
			quote_lines = post['quotedText'].split('\n')
			quote_indent = ' ' * len(indent)
			for line in quote_lines:
				print(f"\n{quote_indent}> {line}", end="")
			print(f" —{post['quotedDate']}", end="")

		for reply in post['replies']:
			print_post(reply, depth + 1)

	for post in posts:
		print_post(post, post.get('external_reply', 0))

directory = sys.argv[1]
posts = read_posts_from_directory(os.path.join(directory, "app.bsky.feed.post"))

root_posts = process_posts(posts)

profile_path = os.path.join(directory, "app.bsky.actor.profile", "self.json")
profile = read_json(profile_path)

print(profile['displayName'])
print()
print(profile['description'])

print_posts(root_posts)
