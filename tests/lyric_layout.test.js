const assert = require("node:assert/strict");
const layout = require("../contents/ui/LyricLayout.js");
const width = text => text.length;

assert.deepEqual(layout.textRows("one two three four five six", 10, width),
                 ["one two", "three four", "five six"]);
assert.deepEqual(layout.textRows("extraordinary word", 6, width),
                 ["extrao", "rdinar", "y", "word"]);
assert.deepEqual(layout.textRows("歌 う 声", 3, width), ["歌 う", "声"]);
assert.deepEqual(layout.textRows("abcdefghijkl", 5, width), ["abcde", "fghij", "kl"]);
assert.deepEqual(layout.textRows("hi abcdefghijkl end", 5, width),
                 ["hi", "abcde", "fghij", "kl", "end"]);

const parts = ["one ", "two ", "three ", "four"].map((words, i) => ({ words, startTimeMs: i * 100 }));
const rows = layout.partRows(parts, 11, width);
assert.deepEqual(rows.flat(), parts);
assert.ok(rows.length > 1);
assert.ok(rows.every(row => row.map(part => part.words).join("").length <= 11));

console.log("Lyric layout tests passed");
