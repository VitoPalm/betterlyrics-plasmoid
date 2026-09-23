#!/usr/bin/env node

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const servicePath = path.join(__dirname, "..", "contents", "ui", "LyricsService.js");
const source = fs.readFileSync(servicePath, "utf8").split("\n").slice(1).join("\n");
const context = { console };
vm.createContext(context);
vm.runInContext(source, context, { filename: servicePath });

const repeated = context.parseLRC(
    "[offset:+100]\n[00:01.00][00:03.00]Hello & goodbye",
    5000
);
assert.equal(repeated.length, 2);
assert.deepEqual(Array.from(repeated, line => line.startTimeMs), [1100, 3100]);

const enhanced = context.parseLRC(
    "[00:01.00][00:03.00]<00:01.00>Hello <00:01.50>world",
    6000
);
assert.equal(enhanced[0].parts[1].startTimeMs, 1500);
assert.equal(enhanced[1].parts[1].startTimeMs, 3500);

const ttml = context.parseTTML(
    '<tt><body><p begin="1s" end="2s"><span begin="1s" end="2s">A &amp; B &#x1f3b5;</span></p></body></tt>',
    3000
);
assert.equal(ttml[0].words, "A & B 🎵");

const styledTtml = context.parseTTML(
    '<tt><body><p begin="1s" end="2s"><span>Styled</span> text</p></body></tt>',
    3000
);
assert.equal(styledTtml[0].words, "Styled text");
assert.equal(styledTtml[0].parts.length, 0);

const nestedTtml = context.parseTTML(
    '<tt><body><p begin="1s" end="3s">Lead <span role="x-bg"><span begin="1.5s" end="2s">(back,</span> '
    + '<span begin="2s" end="2.5s">ground)</span></span></p></body></tt>',
    4000
);
assert.equal(nestedTtml[0].words, "Lead (back, ground)");
assert.equal(nestedTtml[0].words.includes("span"), false);

const plain = context.parsePlainLyrics("[ar:Metadata]\nActual line", 4000);
assert.equal(plain.length, 1);
assert.equal(plain[0].words, "Actual line");

assert.equal(context.extractVideoId("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ");
assert.equal(context.extractVideoId("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ");
assert.equal(context.cleanArtist("Tyler, The Creator"), "Tyler, The Creator");
assert.equal(context.containsNonLatin("Hello 🎵"), false);
assert.equal(context.containsNonLatin("世界"), true);
assert.equal(context.containsNonLatin("Привет"), true);

assert.equal(context.cleanLyricText("A &lt;span&gt;line&lt;/span&gt;/span>", true), "A line");
assert.equal(context.adjustedPositionMs(10000, 250), 9750); // positive = later
assert.equal(context.adjustedPositionMs(10000, -250), 10250); // negative = earlier
assert.equal(context.reconcilePositionMs(10000, 9900, 45, 1200), 9955);
assert.equal(context.reconcilePositionMs(10000, 7000, 45, 1200), 7000); // seek

const timeline = [
    { startTimeMs: 1000, durationMs: 1500 },
    { startTimeMs: 2000, durationMs: 1000 }
];
assert.equal(context.nextTimelineDelayMs(timeline, 0, 1500, 1), 500); // overlapping next line
assert.equal(context.nextTimelineDelayMs(timeline, 0, 1500, 2), 250); // playback rate
assert.equal(context.nextTimelineDelayMs(timeline, 1, 3000, 1), 0); // no further work
assert.equal(context.nextTimelineDelayMs(
    [{ startTimeMs: 0, durationMs: 3000, isInstrumental: true }], 0, 100, 1
), 900); // next instrumental dot

const enriched = { lines: [{ words: "世界" }, { words: "Hello" }] };
assert.equal(context.applyRomanizations(enriched, [{ index: 0, text: "世界" }], ["shì jiè"]), true);
assert.equal(enriched.lines[0].romanization, "shì jiè");
assert.equal(context.applyRomanizations(enriched, [{ index: 1, text: "Hello" }], ["hello"]), false);

const picked = context.chooseBestSearchResult([
    { trackName: "Song", artistName: "Artist", duration: 100, syncedLyrics: "wrong" },
    { trackName: "Song", artistName: "Artist", duration: 201, syncedLyrics: "right" }
], "Song", "Artist", 200, true);
assert.equal(picked.syncedLyrics, "right");

console.log("LyricsService tests passed");
