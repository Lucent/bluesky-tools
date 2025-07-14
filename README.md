# Bluesky Tools

Utilities for downloading and exploring Bluesky accounts via GOAT.

## Usage

- `./install.sh`
  Installs the [GOAT](https://github.com/ronilaukkarinen/goat) repo-fetching tool.

- `./fetch.sh username.bsky.social`
  Fetches the given account's `.car` archive, then:
  - Produces a **threaded plain-text** chronological export
  - Outputs a `.jsonl` file for loading into [Nomic Atlas](https://atlas.nomic.ai)
  - Generates a **heatmap** of post activity
