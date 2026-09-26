// Keep timing-bearing parts intact while wrapping by rendered width.
function rows(items, maxWidth, widthOf, join) {
    if (!items || !items.length) return [];
    var result = [];
    var row = [];
    for (var i = 0; i < items.length; i++) {
        var candidate = row.concat([items[i]]);
        if (row.length && widthOf(join(candidate)) > maxWidth) {
            result.push(row);
            row = [items[i]];
        } else {
            row = candidate;
        }
    }
    if (row.length) result.push(row);

    // Move a boundary item when it makes two adjacent rows more even without
    // causing either row to overflow. This avoids a lone last word.
    for (var j = 0; j + 1 < result.length; j++) {
        while (result[j].length > 1) {
            var before = Math.max(widthOf(join(result[j])), widthOf(join(result[j + 1])));
            var left = result[j].slice(0, -1);
            var right = [result[j][result[j].length - 1]].concat(result[j + 1]);
            var leftWidth = widthOf(join(left));
            var rightWidth = widthOf(join(right));
            if (leftWidth > maxWidth || rightWidth > maxWidth
                    || Math.max(leftWidth, rightWidth) >= before) break;
            result[j] = left;
            result[j + 1] = right;
        }
    }
    return result;
}

function textRows(text, maxWidth, widthOf) {
    var words = (text || "").trim().split(/\s+/).filter(function(word) { return word.length > 0; });
    var result = [];
    var segment = [];
    function flush() {
        if (!segment.length) return;
        var grouped = rows(segment, maxWidth, widthOf, function(items) { return items.join(" "); });
        for (var k = 0; k < grouped.length; k++) result.push(grouped[k].join(" "));
        segment = [];
    }
    for (var i = 0; i < words.length; i++) {
        if (widthOf(words[i]) <= maxWidth) {
            segment.push(words[i]);
            continue;
        }
        flush();
        var chunk = "";
        var characters = Array.from(words[i]);
        for (var j = 0; j < characters.length; j++) {
            if (chunk && widthOf(chunk + characters[j]) > maxWidth) {
                result.push(chunk);
                chunk = "";
            }
            chunk += characters[j];
        }
        if (chunk) result.push(chunk);
    }
    flush();
    return result;
}

function partRows(parts, maxWidth, widthOf) {
    return rows(parts || [], maxWidth, widthOf, function(items) {
        return items.map(function(part) { return part ? (part.words || "") : ""; }).join("");
    });
}

if (typeof module !== "undefined") module.exports = { textRows: textRows, partRows: partRows };
