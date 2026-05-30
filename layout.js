// Pure layout engine for the thread browser: build the visible subgraph from the
// pinned threads, and pack the threads into a tidy forest with flextree. No DOM and
// no text metrics -- node *heights* are measured by the browser (posts are HTML cards
// now) and handed in. The data model is handed in by reference (initLayout). render()
// measures, calls computeLayout, and draws; everything here stays testable under Node.
import { packForest } from "./flexforest/flexforest.js";

// The live data model -- the same object references the page builds and mutates.
let INDEX, children, quotedBy, COLLAPSED, UPCOLLAPSED;
export function initLayout(model) {
	({INDEX, children, quotedBy, COLLAPSED, UPCOLLAPSED} = model);
}

// Box width (also used by the page for the foreignObject / card width) and the gaps
// that separate posts, threads, and satellite quote stacks.
export const NODE_W = 240;
const H_GAP = 26, V_GAP = 46, SAT_GAP = 34, SAT_VGAP = 14;
// The page hands these to the flexforest view as its packer config (the library has no
// hardcoded dimensions); computeLayout's adapter uses them too.
export const GAPS = {hGap: H_GAP, vGap: V_GAP, sideGap: SAT_GAP, sideVGap: SAT_VGAP};

// ---------- graph queries ----------
export function localRoot(rkey) {
	const seen = new Set([rkey]);
	let cur = rkey;
	while (true) {
		const par = INDEX[cur] && INDEX[cur].p;
		if (!par || !INDEX[par] || seen.has(par)) return cur;
		seen.add(par);
		cur = par;
	}
}

export function isLocalRoot(rkey) {
	const e = INDEX[rkey];
	return !e.p || !INDEX[e.p];
}

// Is `a` a reply-ancestor of `b` (climbing parents while they stay in INDEX)?
export function isAncestor(a, b) {
	for (let p = INDEX[b] && INDEX[b].p; p && INDEX[p]; p = INDEX[p].p) if (p === a) return true;
	return false;
}

// An empty reply to someone else's post is noise -- skip it. The exception is
// the trick of replying to an outside post with only a quote of one of our own
// posts, which we keep because it connects that post into our own tree.
export function isNoise(rkey) {
	const e = INDEX[rkey];
	if ((e.t || "").trim()) return false;          // has its own words
	if (!e.p || INDEX[e.p]) return false;           // not a reply to someone else
	return !(e.q || []).some(q => INDEX[q]);        // keep only if it quotes our own post
}

export function descendantCount(rkey, seen) {
	seen = seen || new Set();
	if (seen.has(rkey)) return 0;
	seen.add(rkey);
	let n = 0;
	for (const c of children[rkey]) n += 1 + descendantCount(c, seen);
	return n;
}

// A textless leaf reply to one of our own posts whose only payload is a quote
// is just a connector -- we collapse the empty box and hang its quote straight
// off the parent (drawn with a double border to flag the shortcut).
function isCollapsible(rkey) {
	const e = INDEX[rkey];
	if ((e.t || "").trim()) return false;           // has its own words
	if (!e.p || !INDEX[e.p]) return false;          // must reply to one of our posts
	if (e.img || e.vid || e.ext) return false;      // carries other content
	if (children[rkey].length) return false;        // has replies -- would orphan them
	return e.q && e.q.some(q => INDEX[q]);
}

// ---------- visible subgraph ----------
// Build the union of every pinned thread. Quotes between two visible posts become
// connecting edges; quotes to anything outside stay as satellites.
export function buildVisible(pins, focus) {
	const pinSet = new Set(pins);
	// An up-collapsed node re-roots its thread at itself (hiding its parent, siblings,
	// and everything above), so walk from each thread's display root: the pin itself,
	// unless it holds up-collapses -- then from the deepest ones (a shallower up-collapse
	// is hidden by a deeper one below it).
	const displayRoots = [];
	for (const root of pins) {
		const ups = [...UPCOLLAPSED].filter(rk => INDEX[rk] && localRoot(rk) === root);
		const deep = ups.filter(rk => !ups.some(o => o !== rk && isAncestor(rk, o)));
		displayRoots.push(...(deep.length ? deep : [root]));
	}
	displayRoots.sort();    // canonical order so the arrangement is deterministic
	const tree = new Set();
	for (const root of displayRoots) (function walk(rk) {
		if (tree.has(rk)) return;
		tree.add(rk);
		if (COLLAPSED.has(rk)) return;            // user-collapsed: hide the reply subtree
		for (const c of children[rk]) walk(c);
	})(root);

	// Collapse blank quote-only leaf replies to our own posts: drop the empty box
	// and graft the quoted post into its slot AS A REPLY (it really is one) -- a
	// child via a solid edge, drawn with a double border to flag the shortcut.
	const collapsed = [];
	for (const rk of tree) if (!pinSet.has(rk) && isCollapsible(rk)) collapsed.push(rk);
	for (const rk of collapsed) tree.delete(rk);

	const grafts = new Set();                       // grafted nodes -- drawn double-boxed
	const treeKids = {};                            // per-view child lists (replies + grafts)
	for (const rk of tree) treeKids[rk] = children[rk].filter(c => tree.has(c));

	const quoteEdges = [];   // {from, to}  meaning "from quotes to"
	// An off-tree quote post is one box (satNodeMap) but every link to it gets its
	// own edge (satEdges) -- so a post quoted by several visible posts shows once
	// with several arrows pointing in.
	const satNodeMap = {};   // rkey -> {rkey, anchor, dir}  (placement + badge)
	const satEdges = [];     // {anchor, sat, dir}           (one per quote link)
	const addSat = (q, anchor, dir) => {
		if (!satNodeMap[q]) satNodeMap[q] = {rkey: q, anchor, dir};   // place beside its first linker
		satEdges.push({anchor, sat: q, dir});
	};

	for (const c of collapsed) {
		const anchor = INDEX[c].p;                     // a collapsed leaf's parent is never collapsed
		if (!tree.has(anchor)) continue;
		for (const q of INDEX[c].q || []) {
			if (!INDEX[q]) continue;
			if (tree.has(q)) quoteEdges.push({from: anchor, to: q});   // target already shown -> just link
			else { tree.add(q); treeKids[q] = []; treeKids[anchor].push(q); grafts.add(q); }
		}
	}

	// Quote edges + satellites for the real (non-grafted) tree.
	for (const n of tree) {
		if (grafts.has(n)) continue;                   // grafted leaves carry no further links here
		for (const q of INDEX[n].q || []) {
			if (!INDEX[q]) continue;
			if (tree.has(q)) quoteEdges.push({from: n, to: q});
			else if (!isNoise(q)) addSat(q, n, "out");
		}
		for (const q of quotedBy[n]) {       // in-tree quotes are caught from the other side
			if (!tree.has(q)) addSat(q, n, "in");
		}
	}
	// Re-order display roots by connection along in-tree quote edges, BFS-rooted at the
	// largest thread (most nodes, rkey tie-break). The layout has no global focus -- the
	// "anchor" thread is just whichever has the most content to preserve; clicked quotes
	// then tuck adjacent to their bridge partners and the graph expands outward in the
	// click's direction. Pure function of (pins, quote graph) -> hash bijection preserved.
	if (displayRoots.length > 1) {
		const rootOf = {};
		for (const r of displayRoots) (function walk(rk) {
			if (rootOf[rk]) return;
			rootOf[rk] = r;
			for (const c of treeKids[rk]) walk(c);
		})(r);
		const sizes = {};
		for (const r of displayRoots) sizes[r] = 0;
		for (const k in rootOf) sizes[rootOf[k]]++;
		const adj = {};
		for (const r of displayRoots) adj[r] = new Set();
		for (const {from, to} of quoteEdges) {
			const a = rootOf[from], b = rootOf[to];
			if (a && b && a !== b) { adj[a].add(b); adj[b].add(a); }
		}
		const start = displayRoots.slice().sort((a, b) => sizes[b] - sizes[a] || (a < b ? -1 : 1))[0];
		const order = [], seen = new Set([start]);
		const queue = [start];
		while (queue.length) {
			const r = queue.shift(); order.push(r);
			for (const n of [...adj[r]].sort()) if (!seen.has(n)) { seen.add(n); queue.push(n); }
		}
		for (const r of displayRoots) if (!seen.has(r)) order.push(r);   // isolated -> rkey order (displayRoots is pre-sorted)
		displayRoots.length = 0;
		displayRoots.push(...order);
	}

	return {tree, quoteEdges, satNodes: Object.values(satNodeMap), satEdges, treeKids, grafts, displayRoots};
}

// ---------- forest packing ----------
// Pack a built view into geometry by handing it to flexforest, the app-agnostic packer.
// This is the one seam between thread vocabulary and the library: quote satellites become
// left/right "sidecars" (incoming quotes left, outgoing right), in-tree quote edges become
// generic cross-links (used for bridge alignment), and the page's post gaps become the
// packer's config. heightOf(rk) gives a post's measured pixel height (the page measures the
// HTML card; tests pass a synthetic function). Pure and deterministic given the model +
// heights. The result keeps the page's names (tree/treeKids/satNodes/satPos/...) so render()
// and the test are unchanged -- only the math moved out.
export function computeLayout(view, heightOf) {
	const {tree, quoteEdges, satNodes, satEdges, treeKids, grafts, displayRoots} = view;
	const desc = {
		nodes: tree,
		children: treeKids,
		roots: displayRoots,
		crossEdges: quoteEdges,
		sidecars: satNodes.map(s => ({key: s.rkey, anchor: s.anchor, side: s.dir === "in" ? "left" : "right"})),
	};
	const config = {nodeW: NODE_W, ...GAPS};
	const {pos, sidecarPos, bounds} = packForest(desc, heightOf, config);
	// sidecar keys are the satellite rkeys, so sidecarPos is satPos under the page's name.
	return {tree, treeKids, grafts, quoteEdges, satNodes, satEdges, pos, satPos: sidecarPos, bounds};
}
