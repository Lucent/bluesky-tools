// Layout regression test. Imports the REAL engine (layout.js) — the same code the
// page runs — so there's nothing to drift. Builds the model from index.json the way
// the page does, then asserts the invariants we keep breaking by hand:
//   • no two post boxes overlap, in any single thread or merged pair
//   • every reply sits below its parent (no inverted edges)
//   • an up-fold re-roots cleanly (focus thread's box count shrinks, still no overlap)
// Run: node test_layout.mjs
import fs from "fs";
import { initLayout, buildVisible, computeLayout, localRoot, NODE_W } from "./layout.js";

// The page measures each post's HTML card; under Node we stand in a deterministic
// height (a few text lines + a chunk per media item). It need not be pixel-accurate —
// the test exercises the PACKING (overlaps, inversions, re-rooting), given heights.
const synthH = (rk) => {
	const e = INDEX[rk];
	const lines = Math.max(1, Math.ceil(((e.t || "").length) / 34));
	let h = 34 + lines * 16;
	if (e.img) h += e.img.length * 126;
	if (e.ext && e.ext.u && !e.tweet) h += 70;
	if (e.vid) h += 40;
	return h;
};

const data = JSON.parse(fs.readFileSync(new URL("./index.json", import.meta.url)));
const INDEX = data.posts, children = {}, quotedBy = {};
for (const rk in INDEX) { children[rk] = []; quotedBy[rk] = []; }
for (const rk in INDEX) {
	const e = INDEX[rk];
	if (e.p && INDEX[e.p]) children[e.p].push(rk);
	for (const q of e.q || []) if (INDEX[q]) quotedBy[q].push(rk);
}
for (const k in children) children[k].sort((a, b) => (INDEX[a].d || "").localeCompare(INDEX[b].d || ""));
const COLLAPSED = new Set(), UPCOLLAPSED = new Set();
initLayout({ INDEX, children, quotedBy, COLLAPSED, UPCOLLAPSED });

// Pack a pinned set and check it: the view is built, then computeLayout places it.
const layoutOf = (pins) => computeLayout(buildVisible(pins), synthH);
function overlaps(L) {
	const b = [...L.tree].map(rk => ({ x: L.pos[rk].x, y: L.pos[rk].y, w: NODE_W, h: synthH(rk) }));
	let n = 0;
	for (let i = 0; i < b.length; i++) for (let j = i + 1; j < b.length; j++) {
		const ox = Math.min(b[i].x + b[i].w, b[j].x + b[j].w) - Math.max(b[i].x, b[j].x);
		const oy = Math.min(b[i].y + b[i].h, b[j].y + b[j].h) - Math.max(b[i].y, b[j].y);
		if (ox > 1 && oy > 1) n++;
	}
	return n;
}
const inversions = (L) => {
	let n = 0;
	for (const rk of L.tree) for (const c of L.treeKids[rk]) if (L.pos[c].y <= L.pos[rk].y + 1) n++;
	return n;
};

let fails = 0;
const check = (name, cond, detail) => { if (!cond) { fails++; console.log(`FAIL  ${name}  ${detail}`); } };

// Distinct cross-thread bridged pairs (and the single threads themselves).
const seen = new Set(), pairs = [];
for (const rk in INDEX) for (const q of INDEX[rk].q || []) {
	if (!INDEX[q] || INDEX[q].tweet || INDEX[rk].tweet) continue;
	const ra = localRoot(rk), rb = localRoot(q);
	if (ra === rb) continue;
	const key = [ra, rb].sort().join("+");
	if (!seen.has(key)) { seen.add(key); pairs.push([ra, rb]); }
}

let singles = 0, merged = 0, upfolds = 0;
const roots = new Set(pairs.flat());
for (const r of roots) { const L = layoutOf([r]); check("single", overlaps(L) === 0 && inversions(L) === 0, r); singles++; }
for (const [a, b] of pairs) { const L = layoutOf([a, b]); check("merge", overlaps(L) === 0 && inversions(L) === 0, `${a}+${b}`); merged++; }
// up-fold: re-root a thread at a mid node and confirm it shrinks and stays clean.
for (const r of roots) {
	const mid = children[r].find(c => children[c].length);
	if (!mid) continue;
	const full = layoutOf([r]).tree.size;
	UPCOLLAPSED.add(mid);
	const L = layoutOf([r]);
	UPCOLLAPSED.delete(mid);
	check("upfold-clean", overlaps(L) === 0 && inversions(L) === 0, `${r}@${mid}`);
	check("upfold-shrinks", L.tree.size < full && !L.tree.has(r), `${r}@${mid}`);
	upfolds++;
}

console.log(`checked ${singles} single, ${merged} merged, ${upfolds} up-folded views`);
console.log(fails ? `\n${fails} FAILURES` : "\nall layout invariants hold");
process.exit(fails ? 1 : 0);
