# bluesky-tools (thread browser) — agent & style guide

An interactive pan/zoom view of Bluesky threads: assembles a post's full reply tree, draws
quotes beside the posts that make them, pulls any post on demand. Static files, no build step,
no server logic beyond a file host. The layout/animation engine is **flexforest** (a git
submodule); this repo is the thread-specific *app* on top of it.

## Craft doctrine

Single-developer craft, not a product built to spec. Lean, modern, no frameworks. The browser
and its cascade are powerful engines we **leverage, never steamroll**.

- **CSS is a logic/compute engine, not a paint layer.** Anything the cascade can read and act
  on — selection, mode, motion — lives in CSS; JS writes it. Durations/easings/rates/geometry
  constants are CSS custom properties and are the **source of truth**; JS reads them back only
  to compute what CSS can't (an SVG path). Never move into JS what CSS can own.
- **The DOM is the state store.** The painted SVG is the truth for what's on screen; the data
  model (`INDEX`) is the truth for the data; the **hash** is the canonical, shareable truth
  for the view. Each fact has one home — no parallel structures restating another.
- **No speculative error handling. No fallbacks. No feature detection.** Trust invariants and
  let impossible states crash loudly. Validate only at true boundaries (the API, the URL,
  user input). Newest JS/CSS available; no compat shims.
- **Minimal, root-cause, no exceptions.** Do exactly the thing; add no code, counter-hacks, or
  guards. Fix the cause, not the symptom (e.g. the fold-memory bug was fixed in
  `pruneCollapsed`, not by bolting state onto the toggles). If the right implementation needs
  a special case, the abstraction is wrong. Kill dead code; don't fix it.
- **Separate compute from apply.** `layout.js` is pure and Node-tested; `browse.html` does the
  DOM/fetch/IO. Pure functions compute and return; they don't also mutate the DOM.
- **Comments explain why, not what.** Dense, load-bearing.
- **Conventions.** Tabs, not spaces. Braceless single-statement `if`/`else`; multi-line gets
  braces. `function` for named declarations, arrows for callbacks/one-liners. ESM only.
  **Served `.js`/`.css` stay ASCII** (no charset header ⇒ no encoding guessing); non-ASCII
  only in charset-declared HTML or as `\u`/CSS escapes.
- **Runtime is no-build.** Static files served as-is; the Docker build only assembles them.

## Architecture

- **`layout.js`** — the pure, DOM-free layer. `buildVisible` builds the visible subgraph from
  the pinned threads (quotes → connecting edges or beside-the-post satellites; noise/graft/
  up-root semantics); `computeLayout` is the thin **adapter** that maps thread vocabulary onto
  flexforest's neutral description and calls `packForest`. No DOM, no text metrics — heights
  are measured by the view and handed in. Runs and is asserted under Node.
- **`browse.html`** — the app: the `INDEX` data model, API fetch/normalize, post-card HTML
  (`postHTML`), hash routing, and the flexforest callbacks. It constructs the view with
  `layered: false` (threads are variable-height) and supplies `renderNode` / `nodeClass` /
  `edgeClass` / `onActivate` / `onFold`.
- **`flexforest/`** — the submodule (see its AGENTS.md). Owns geometry, the SVG DOM,
  reconcile, the two motion timelines, camera, and pointers. This app never touches library
  internals except via the callbacks and `getElement`.
- **`test_layout.mjs`** — imports the real `layout.js` and replays ~1,600 views asserting zero
  box overlaps and zero inverted edges. Keep it green; it's the guard on the pure engine.

## Hash is the source of truth — and canonical

`#focus;pins;down-folds;up-folds`. A given view yields exactly one hash and a hash rebuilds
exactly one view (bijection). The session **set** may remember more than the hash: a fold
hidden under a higher fold stays in `COLLAPSED`/`UPCOLLAPSED` (so re-expanding restores it),
but `effectiveFolds()` computes the canonical visible subset that the hash serialises.
`pruneCollapsed` drops only folds the user can no longer reach (node gone / thread unpinned),
never merely-hidden ones. Don't conflate session memory with the canonical hash.

## Deploy

Two-stage Docker: the build stage parses the `.car` archive into `index.json` and assembles
`/site`; the runtime stage serves it with `serve.py`. The server adds a **content ETag** and
answers `If-None-Match` with `304`, plus `Cache-Control: max-age=0, must-revalidate` — so a
redeploy never pairs a fresh `index.html` with a stale cached module. Cloudflare is set to
**respect origin headers**, so it revalidates and propagates on the next request — no purge,
no `no-cache`. Build + deploy: `./build.sh && docker compose up -d`. Behind a Cloudflare
tunnel at `threads.lucent.tools`. The user verifies UI changes in the browser themselves.
