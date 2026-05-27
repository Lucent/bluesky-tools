// Pure layout engine for the thread browser: build the visible subgraph from the
// pinned threads, and pack the threads into a tidy forest with flextree. No DOM and
// no text metrics — node *heights* are measured by the browser (posts are HTML cards
// now) and handed in. The data model is handed in by reference (initLayout). render()
// measures, calls computeLayout, and draws; everything here stays testable under Node.
import { flextree } from "./flextree.js";

// The live data model — the same object references the page builds and mutates.
let INDEX, children, quotedBy, COLLAPSED, UPCOLLAPSED;
export function initLayout(model) {
	({INDEX, children, quotedBy, COLLAPSED, UPCOLLAPSED} = model);
}

// Box width (also used by the page for the foreignObject / card width) and the gaps
// that separate posts, threads, and satellite quote stacks.
export const NODE_W = 240;
const H_GAP = 26, V_GAP = 46, SAT_GAP = 34, SAT_VGAP = 14;

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

// An empty reply to someone else's post is noise — skip it. The exception is
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
// is just a connector — we collapse the empty box and hang its quote straight
// off the parent (drawn with a double border to flag the shortcut).
function isCollapsible(rkey) {
	const e = INDEX[rkey];
	if ((e.t || "").trim()) return false;           // has its own words
	if (!e.p || !INDEX[e.p]) return false;          // must reply to one of our posts
	if (e.img || e.vid || e.ext) return false;      // carries other content
	if (children[rkey].length) return false;        // has replies — would orphan them
	return e.q && e.q.some(q => INDEX[q]);
}

// ---------- visible subgraph ----------
// Build the union of every pinned thread. Quotes between two visible posts become
// connecting edges; quotes to anything outside stay as satellites.
export function buildVisible(pins) {
	const pinSet = new Set(pins);
	// An up-collapsed node re-roots its thread at itself (hiding its parent, siblings,
	// and everything above), so walk from each thread's display root: the pin itself,
	// unless it holds up-collapses — then from the deepest ones (a shallower up-collapse
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
	// and graft the quoted post into its slot AS A REPLY (it really is one) — a
	// child via a solid edge, drawn with a double border to flag the shortcut.
	const collapsed = [];
	for (const rk of tree) if (!pinSet.has(rk) && isCollapsible(rk)) collapsed.push(rk);
	for (const rk of collapsed) tree.delete(rk);

	const grafts = new Set();                       // grafted nodes — drawn double-boxed
	const treeKids = {};                            // per-view child lists (replies + grafts)
	for (const rk of tree) treeKids[rk] = children[rk].filter(c => tree.has(c));

	const quoteEdges = [];   // {from, to}  meaning "from quotes to"
	// An off-tree quote post is one box (satNodeMap) but every link to it gets its
	// own edge (satEdges) — so a post quoted by several visible posts shows once
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
			if (tree.has(q)) quoteEdges.push({from: anchor, to: q});   // target already shown → just link
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
	return {tree, quoteEdges, satNodes: Object.values(satNodeMap), satEdges, treeKids, grafts, displayRoots};
}

// ---------- forest packing ----------
// Pack a built view into geometry. heightOf(rk) gives a post's measured pixel height
// (the page measures the HTML card; tests pass a synthetic function). Returns box
// top-left positions (pos), satellite positions (satPos), and the bounding box. Pure
// and deterministic given the model + heights.
export function computeLayout(view, heightOf) {
	const {tree, quoteEdges, satNodes, satEdges, treeKids, grafts, displayRoots} = view;
	const H = heightOf;

	// Quote satellites split by direction so a post can use both gutters: incoming
	// quotes (posts that quote this one) stack to its left, outgoing quotes (posts
	// or tweets this one quotes) to its right. A gutter is reserved per populated side.
	const satsIn = {}, satsOut = {};
	for (const s of satNodes) {
		const m = s.dir === "in" ? satsIn : satsOut;
		(m[s.anchor] || (m[s.anchor] = [])).push(s);
	}
	const stackH = (list) => list && list.length ? list.reduce((a, s) => a + H(s.rkey), 0) + SAT_VGAP * (list.length - 1) : 0;
	const gutterW = (list) => list && list.length ? SAT_GAP + NODE_W : 0;
	const leftG = (rk) => gutterW(satsIn[rk]);
	const allocW = (rk) => leftG(rk) + NODE_W + gutterW(satsOut[rk]);
	const rowH = (rk) => Math.max(H(rk), stackH(satsIn[rk]), stackH(satsOut[rk]));

	// Lay each pinned thread as its OWN upright tidy tree — parents above, replies
	// below, packed by contour (flextree). Threads are then set side-by-side: a merged
	// thread is woven in *beside* the one it quotes (never re-rooted), shifted
	// vertically so the quote arrow runs straight across between the two linked posts,
	// and tucked horizontally by contour so a short thread nestles into a tall
	// neighbour's empty space. Each thread keeps its natural orientation, spanning up
	// (its ancestors) and down (its replies) on its own.
	const fl = flextree()
		.nodeSize(d => [allocW(d.data.rk), rowH(d.data.rk) + V_GAP])
		.spacing(() => H_GAP);
	const toData = (rk) => ({rk, children: treeKids[rk].map(toData)});

	// Contour tuck: rightOf[y-bin] = furthest-right edge of everything placed so far.
	// A new thread slides right only as far as its own left contour needs to clear
	// that profile by H_GAP — so it slips into vertical gaps instead of a flat band.
	const BIN = 8;
	const rightOf = new Map();
	const span = (y, rk) => [y, y + rowH(rk) + V_GAP];
	const cxy = {};
	displayRoots.forEach((root, k) => {
		const t = fl.hierarchy(toData(root));
		fl(t);
		const local = {};
		t.each(n => { local[n.data.rk] = {x: n.x, y: n.y}; });

		// vertical: line this subtree's bridge post up with its already-placed partner
		let dy = 0;
		if (k > 0) {
			const link = quoteEdges.find(e =>
				(local[e.from] && cxy[e.to]) || (local[e.to] && cxy[e.from]));
			if (link) {
				const mine = local[link.from] ? link.from : link.to;
				dy = cxy[mine === link.from ? link.to : link.from].y - local[mine].y;
			}
		}

		// horizontal: smallest shift that clears the placed contour where they overlap
		let dx = 0;
		if (k > 0) {
			dx = -Infinity;
			for (const rk in local) {
				const [lo, hi] = span(local[rk].y + dy, rk), left = local[rk].x - allocW(rk) / 2;
				for (let b = Math.floor(lo / BIN); b <= Math.ceil(hi / BIN); b++)
					if (rightOf.has(b)) dx = Math.max(dx, rightOf.get(b) + H_GAP - left);
			}
			if (dx === -Infinity) dx = 0;   // no vertical overlap with anything placed
		}

		for (const rk in local) {
			const x = local[rk].x + dx, y = local[rk].y + dy;
			cxy[rk] = {x, y};
			const [lo, hi] = span(y, rk), right = x + allocW(rk) / 2;
			for (let b = Math.floor(lo / BIN); b <= Math.ceil(hi / BIN); b++)
				rightOf.set(b, Math.max(rightOf.get(b) ?? -Infinity, right));
		}
	});

	// Convert centres → top-left boxes; drop each satellite stack into its gutter,
	// vertically centred on the post (incoming left, outgoing right).
	const pos = {}, satPos = {};
	const stackInto = (list, x, cy) => {
		if (!list) return;
		let y = cy - stackH(list) / 2;
		for (const s of list) { satPos[s.rkey] = {x, y}; y += H(s.rkey) + SAT_VGAP; }
	};
	for (const rk of tree) {
		const c = cxy[rk], boxLeft = c.x - allocW(rk) / 2, postLeft = boxLeft + leftG(rk);
		const mid = c.y + (rowH(rk) + V_GAP) / 2;                  // flextree's y is the box top; centre content in the row
		pos[rk] = {x: postLeft, y: mid - H(rk) / 2};
		stackInto(satsIn[rk], boxLeft, mid);                       // left gutter
		stackInto(satsOut[rk], postLeft + NODE_W + SAT_GAP, mid);  // right gutter
	}

	// Bounding box over every placed box (tree + satellites, which may sit left or below).
	let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
	for (const rk of tree) {
		minX = Math.min(minX, pos[rk].x); minY = Math.min(minY, pos[rk].y);
		maxX = Math.max(maxX, pos[rk].x + NODE_W); maxY = Math.max(maxY, pos[rk].y + H(rk));
	}
	for (const s of satNodes) {
		const p = satPos[s.rkey];
		minX = Math.min(minX, p.x); minY = Math.min(minY, p.y);
		maxX = Math.max(maxX, p.x + NODE_W); maxY = Math.max(maxY, p.y + H(s.rkey));
	}

	return {tree, treeKids, grafts, quoteEdges, satNodes, satEdges, pos, satPos, bounds: [minX, minY, maxX, maxY]};
}
