# Bluesky Tools

Utilities for downloading and exploring Bluesky accounts via goat.

## Usage

- `./install.sh`
  Installs the [goat](https://github.com/bluesky-social/indigo/blob/main/cmd/goat/README.md) repo-fetching tool.

- `./fetch.sh username.bsky.social`
  Fetches the given account's `.car` archive, then:
  - Produces a **threaded plain-text** chronological export
  - Outputs a `.jsonl` file for loading into [Nomic Atlas](https://atlas.nomic.ai)
  - Generates a **heatmap** of post activity

- `python thread_graph.py did:plc:... 3jtc66csqyr2o > post.mmd`
  Emits a Mermaid flowchart for the entire thread containing that post (ancestors + every reply branch), shows every post that quotes it, and follows any quoted posts (recursively) to include their own replies/quotes. Render the `.mmd` text with [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) or another viewer to produce an SVG.
