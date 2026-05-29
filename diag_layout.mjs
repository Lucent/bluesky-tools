// Replay layout decisions for a specific scenario, dumping coords + bounds.
import {initLayout, buildVisible, computeLayout, localRoot, NODE_W} from "./layout.js";
import fs from "node:fs";

const data = JSON.parse(fs.readFileSync("./index.json", "utf8"));
const INDEX = data.posts;
const children = {}, quotedBy = {};
for (const rk in INDEX) { children[rk] = []; quotedBy[rk] = []; }
for (const rk in INDEX) {
	const e = INDEX[rk];
	if (e.p && INDEX[e.p]) children[e.p].push(rk);
	for (const q of e.q || []) if (INDEX[q]) quotedBy[q].push(rk);
}
const COLLAPSED = new Set(), UPCOLLAPSED = new Set();
initLayout({INDEX, children, quotedBy, COLLAPSED, UPCOLLAPSED});

const H = (rk) => INDEX[rk].tweet ? 60 : 100;

function subtreeBox(rk, pos, treeKids) {
	let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, n = 0;
	const stack = [rk], seen = new Set();
	while (stack.length) {
		const k = stack.pop(); if (seen.has(k)) continue; seen.add(k);
		const p = pos[k]; if (p) {
			minX = Math.min(minX, p.x); minY = Math.min(minY, p.y);
			maxX = Math.max(maxX, p.x + NODE_W); maxY = Math.max(maxY, p.y + H(k));
			n++;
		}
		for (const c of (treeKids[k] || [])) stack.push(c);
	}
	return {minX, minY, maxX, maxY, n};
}

function dump(label, focus, pins) {
	const view = buildVisible(pins, focus);
	const result = computeLayout(view, H);
	const {pos, satPos, bounds, quoteEdges, treeKids, _skyline} = result;
	const {displayRoots} = view;
	console.log(`\n=== ${label} ===`);
	console.log("PINS         :", pins.join(" , "));
	console.log("displayRoots :", displayRoots.join(" , "));
	console.log("scene bounds : x∈[" + bounds[0].toFixed(0) + "," + bounds[2].toFixed(0) + "]  y∈[" + bounds[1].toFixed(0) + "," + bounds[3].toFixed(0) + "]");
	console.log("focus pos    :", pos[focus] && {x: pos[focus].x.toFixed(0), y: pos[focus].y.toFixed(0)});
	for (const r of displayRoots) {
		const b = subtreeBox(r, pos, treeKids);
		console.log(`  thread ${r}: ${b.n} nodes  x∈[${b.minX.toFixed(0)},${b.maxX.toFixed(0)}]  y∈[${b.minY.toFixed(0)},${b.maxY.toFixed(0)}]`);
		// per-node detail
		const stack = [r], seen = new Set();
		while (stack.length) {
			const k = stack.pop(); if (seen.has(k)) continue; seen.add(k);
			const p = pos[k]; if (p) console.log(`     ${k}  pos=(${p.x.toFixed(0)},${p.y.toFixed(0)})  right=${(p.x + NODE_W).toFixed(0)}`);
			for (const c of (treeKids[k] || [])) stack.push(c);
		}
	}
	if (quoteEdges.length) {
		console.log("quoteEdges:");
		for (const e of quoteEdges) {
			const pf = pos[e.from], pt = pos[e.to];
			if (pf && pt) console.log(`  ${e.from} (${pf.x.toFixed(0)},${pf.y.toFixed(0)}) → ${e.to} (${pt.x.toFixed(0)},${pt.y.toFixed(0)})   Δx=${(pt.x-pf.x).toFixed(0)} Δy=${(pt.y-pf.y).toFixed(0)}`);
		}
	}
	console.log("sats:");
	for (const s of view.satNodes) {
		const p = satPos[s.rkey];
		console.log(`  ${s.rkey} dir=${s.dir} anchor=${s.anchor}  at (${p.x.toFixed(0)},${p.y.toFixed(0)})`);
	}
	// Skyline near the bridge y, to see what's pushing the new thread right
	const yBridge = quoteEdges[0] && pos[quoteEdges[0].from] && pos[quoteEdges[0].from].y;
	if (yBridge != null) {
		const bin = Math.floor(yBridge / 8);
		console.log(`skyline near bridge y=${yBridge.toFixed(0)} (bins ${bin-3}..${bin+15}):`);
		const cols = [];
		for (let b = bin - 3; b <= bin + 15; b++) {
			cols.push(`${b}:[L=${_skyline.leftOf.get(b)?.toFixed(0) ?? "-"} R=${_skyline.rightOf.get(b)?.toFixed(0) ?? "-"}]`);
		}
		console.log("  " + cols.join("  "));
	}
}

const focus = "3jwiuqwq5z22i";
const merged = "3ju2ix5wz7s2n";
const r1 = localRoot(focus), r2 = localRoot(merged);
console.log("focus  =", focus, " localRoot:", r1);
console.log("merged =", merged, " localRoot:", r2);

dump("BEFORE: single thread, focus=3jwi...", focus, [r1]);
// In toggleThread, ctrl-click sets the NEW focus = the clicked rkey.
dump("AFTER : focus is now 3ju2... (clicked)", merged, [r1, r2]);
