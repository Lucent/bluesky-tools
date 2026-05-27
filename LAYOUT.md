# Thread browser

An interactive pan/zoom view of Bluesky threads. It assembles a post's full reply
tree, draws quotes beside the posts that make them, and pulls any post on the network
on demand. Static files, no build step, no framework, no server logic beyond a file
host.

## Files

- `browse.html` — the page: styles, post-card HTML, SVG rendering, interaction, fetch,
  and URL/hash routing. One inline ES module.
- `layout.js` — the pure layout engine (no DOM): visible-subgraph construction and the
  flextree forest packing. Takes the data model by reference and a height lookup;
  returns geometry.
- `flextree.js` — vendored d3-flextree (van der Ploeg non-layered tidy tree), converted
  from UMD to an ES module. No runtime dependencies.
- `thread_browser.py` — builds `index.json` from a local `.car` archive. Pure stdlib.
- `test_layout.mjs` — imports the real engine and asserts layout invariants.

## Data model

One store, `INDEX`, keyed by record key (rkey). Entries are compact:
`{ t, d, p?, q?, img?, ext?, vid?, f?, external?, did?, handle?, name?, avatar?, xr?, xrd?, xp? }`.

`index.json` (built from the `.car`) is an optional cache. Present, it fills `INDEX`
and powers the sidebar thread list and free-text search. Absent, the app runs API-only:
blank sidebar, every view resolved through the URL field. Either way the public AppView
(`getPostThread`, no auth) tops up `INDEX` on demand — one post or one thread becomes
"already in `INDEX`? use it : fetch it." Fetched posts are normalized into the same
compact shape, so rendering never distinguishes source.

A post is addressed by rkey within the archive (one repo, so rkeys are unambiguous) and
by `did/rkey` anywhere else (rkeys are repo-scoped and can't be resolved to a DID, so
the DID travels in the hash). The two forms coexist in the hash; internal keys stay bare
rkey.

## Layout

The packing is **d3-flextree** — van der Ploeg's *non-layered tidy tree* (Software:
Practice and Experience, 2014), the variable-size successor to Reingold–Tilford (1981)
and the linear-time Walker/Buchheim–Jünger–Leipert line (2002). Properties:

- **Tidy.** Parents centered over children; isomorphic subtrees drawn identically;
  minimum width; no node overlaps.
- **Non-layered.** A child sits a fixed gap below its parent's actual bottom, not on a
  global per-depth row. Posts have variable height, so rows would clip or waste space.
- **Linear time.** Contour tracking with threads and modifier/shift aggregation: subtree
  separation is computed without re-walking, displacements applied in one pass.

On top of the library:

- **Measured heights.** Each post renders once in an offscreen HTML card; its pixel
  height feeds flextree's `nodeSize`. Measuring (DOM) is separated from packing (pure),
  so the engine runs and tests under Node.
- **Satellite gutters.** Quotes and quoted-by posts sit in left/right gutters. Their
  width is folded into the node's reserved footprint (`allocW`), so flextree's own
  contour separation keeps neighboring subtrees clear of them — collision avoidance for
  satellites falls out of the tidy-tree machinery, with no separate pass.
- **Forest tuck.** Multiple pinned threads are each laid out, then packed side by side
  against a y-binned right-edge skyline: a new thread slides left until its left contour
  clears the running profile by one gap. A short thread nestles into a tall neighbor's
  vertical gap instead of reserving a bounding-box column.
- **Bridge alignment.** A merged thread is shifted in y so its quoted post lines up with
  the post linking to it, and the quote arrow runs across.
- **Deterministic.** Display roots are sorted, so the same set of threads always packs
  identically — which lets the hash be a bijection with the rendered graph.

Overlap freedom is by theorem within a tree (contour separation) and verified across
trees: `test_layout.mjs` replays 1,586 views (single, merged, up-folded) and asserts
zero box overlaps and zero inverted edges via AABB tests.

Merging keeps each thread upright. Inverting a bridged thread's ancestors (mirroring them
upward) was rejected: flextree reserves space one-directionally, so an up-mirrored branch
lands on the focus thread — measured to collide in 168 of 611 merges.

## Rendering

A post is an HTML `<article>` inside an SVG `<foreignObject>`. The browser wraps the
text, lays out images/cards/video, and reports the height. SVG draws only the box rect
(border/fill, color variants), the edges (bezier paths; quotes dashed with an arrowhead),
and the fold toggles. This keeps the SVG node count to a handful per post.

Colors are authorship-relative: a post by the same author as its thread's root gets the
plain card; a reply by anyone else is tinted; a quoted tweet is blue; off-tree quotes are
gold with a dashed border and arrow. Names link to profiles; dates link to the post.

Camera is `tx/ty/scale` with pointer/wheel/pinch; navigation animates only when the new
view shares a thread with the last, otherwise hard-cuts.

## Folding

- **Down** (bottom of a node): hides the reply subtree below; the tag points down and
  shows the hidden count.
- **Up** (top of a node): re-roots the thread there, hiding the parent, siblings, and
  everything above; the tag points up. Implemented by walking the visible subgraph from
  the deepest up-folded node instead of the pin.

Both fold sets are pruned to what actually shapes the view (folds in unpinned threads, or
hidden under a higher fold, are dropped) so the hash stays canonical.

## Hash

`#<focus>;<pinnedRoots>;<down-folded>;<up-folded>` — four comma-lists, the last three
sorted, trailing empties trimmed. The hash is the single source of truth for everything
but zoom: every navigation, merge, and fold writes it; restoring reads it and fetches any
post it names. A given view always produces one hash, and a hash always rebuilds the same
view. The header URL field mirrors the hash and accepts an `at://` URI or a `bsky.app`
post URL.

## Running

Local, no Docker:

    python3 thread_browser.py did:plc:xxxxxxxx --serve 8000

Builds `index.json` from the `did:plc:…` archive folder and serves the directory; open
`http://localhost:8000/browse.html`. Needs internet (it pulls outside posts and images
from the public API/CDN at view time).

With no archive, open `browse.html` from any static host and paste a post URL — the tool
runs entirely against the API.
