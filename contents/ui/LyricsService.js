.pragma library

// Cache: key -> { syncType: "syllable"|"line"|"none", lines: Array, source: string }
var lyricsCache = {};
var lyricsCacheOrder = [];
var MAX_CACHE_ENTRIES = 40;

function getCachedLyrics(key) {
    if (!Object.prototype.hasOwnProperty.call(lyricsCache, key)) return null;
    var index = lyricsCacheOrder.indexOf(key);
    if (index >= 0) lyricsCacheOrder.splice(index, 1);
    lyricsCacheOrder.push(key);
    return lyricsCache[key];
}

function cacheLyrics(key, result) {
    var index = lyricsCacheOrder.indexOf(key);
    if (index >= 0) lyricsCacheOrder.splice(index, 1);
    lyricsCache[key] = result;
    lyricsCacheOrder.push(key);
    while (lyricsCacheOrder.length > MAX_CACHE_ENTRIES) {
        delete lyricsCache[lyricsCacheOrder.shift()];
    }
}

function decodeXmlText(value) {
    return (value || "")
        .replace(/&#(x[0-9a-f]+|\d+);/gi, function(match, code) {
            var radix = code.charAt(0).toLowerCase() === "x" ? 16 : 10;
            var digits = radix === 16 ? code.slice(1) : code;
            var point = parseInt(digits, radix);
            if (!isFinite(point) || point < 0 || point > 0x10ffff) return match;
            if (point <= 0xffff) return String.fromCharCode(point);
            point -= 0x10000;
            return String.fromCharCode(0xd800 + (point >> 10), 0xdc00 + (point & 0x3ff));
        })
        .replace(/&quot;/gi, "\"")
        .replace(/&apos;/gi, "'")
        .replace(/&lt;/gi, "<")
        .replace(/&gt;/gi, ">")
        .replace(/&amp;/gi, "&");
}

function cleanLyricText(value, collapseWhitespace) {
    var text = decodeXmlText(value || "")
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/<[^>]*>/g, "")
        .replace(/\/(?:span|p|div|body|tt)\s*>/gi, "")
        .replace(/[\u200b\ufeff]/g, "");
    return collapseWhitespace ? text.replace(/\s+/g, " ").trim() : text;
}

// A positive value means what the UI says: render the lyrics later. Keeping
// this conversion in one place prevents line selection and word fill from
// accidentally using opposite offset signs.
function adjustedPositionMs(playbackPositionMs, lyricDelayMs) {
    var position = Number(playbackPositionMs) || 0;
    var delay = Number(lyricDelayMs) || 0;
    return Math.max(0, position - delay);
}

// Return the next static visual change. Word fills keep their own animation
// clock; line-only lyrics need to wake only at boundaries and break markers.
function nextTimelineDelayMs(lines, activeIndex, positionMs, playbackRate) {
    var position = Number(positionMs) || 0;
    var next = Number.POSITIVE_INFINITY;
    for (var i = 0; i < lines.length; i++) {
        var start = Number(lines[i].startTimeMs) || 0;
        var end = start + (Number(lines[i].durationMs) || 0);
        if (start > position && start < next) next = start;
        if (end > position && end < next) next = end;
    }
    var line = lines[activeIndex];
    if (line && line.isInstrumental && line.durationMs > 0) {
        for (var dot = 1; dot <= 2; dot++) {
            var threshold = line.startTimeMs + line.durationMs * dot / 3;
            if (threshold > position && threshold < next) next = threshold;
        }
    }
    if (!isFinite(next)) return 0;
    var rate = Math.max(0.1, Number(playbackRate) || 1);
    return Math.max(16, Math.min(60000, Math.ceil((next - position) / rate)));
}

// MPRIS samples arrive much less often than the animation clock. Snap on real
// seeks, but gently converge small sample errors to avoid a backward jump on
// every position probe.
function reconcilePositionMs(projectedPositionMs, samplePositionMs, maxCorrectionMs, snapThresholdMs) {
    var projected = Number(projectedPositionMs) || 0;
    var sample = Number(samplePositionMs) || 0;
    var difference = sample - projected;
    if (Math.abs(difference) >= snapThresholdMs) return Math.max(0, sample);
    return Math.max(0, projected + Math.max(-maxCorrectionMs, Math.min(maxCorrectionMs, difference)));
}

function parseTTMLTime(t) {
    if (!t) return 0;
    if (typeof t === "number") return t;
    var matchUnit = t.match(/^([\d.]+)(h|m|s|ms)$/);
    if (matchUnit) {
        var val = parseFloat(matchUnit[1]);
        var unit = matchUnit[2];
        if (unit === "h") return Math.round(val * 3600000);
        if (unit === "m") return Math.round(val * 60000);
        if (unit === "s") return Math.round(val * 1000);
        if (unit === "ms") return Math.round(val);
    }
    var parts = t.split(":").map(function(r) { return r.replace(/[^0-9.]/g, ""); });
    var ms = 0;
    if (parts.length === 1) {
        ms = parseFloat(parts[0]) * 1000;
    } else if (parts.length === 2) {
        ms = parseInt(parts[0], 10) * 60000 + parseFloat(parts[1]) * 1000;
    } else if (parts.length === 3) {
        ms = parseInt(parts[0], 10) * 3600000 + parseInt(parts[1], 10) * 60000 + parseFloat(parts[2]) * 1000;
    }
    return isFinite(ms) && ms >= 0 ? Math.round(ms) : 0;
}

function parsePlainLyrics(plainText, songDurationMs) {
    if (!plainText) return [];
    var rawLines = plainText.split(/\r?\n/);
    var cleanLines = [];
    for (var i = 0; i < rawLines.length; i++) {
        var t = cleanLyricText(rawLines[i], true);
        if (t.length > 0 && !/^\[(ar|ti|al|by|offset|length|re|ve):/i.test(t)) {
            cleanLines.push(t);
        }
    }
    if (cleanLines.length === 0) return [];
    var totalDur = songDurationMs > 0 ? songDurationMs : (cleanLines.length * 4000);
    var step = totalDur / cleanLines.length;
    var result = [];
    for (var j = 0; j < cleanLines.length; j++) {
        result.push({
            startTimeMs: Math.round(j * step),
            durationMs: Math.round(step),
            words: cleanLines[j],
            parts: [],
            isInstrumental: false,
            isUnsynced: true
        });
    }
    return result;
}

function parseTTML(xmlText, songDurationMs) {
    if (!songDurationMs) songDurationMs = 0;
    var timedLines = [];
    var plainLines = [];
    var pRegex = /<p\b([^>]*)>([\s\S]*?)<\/p>/gi;
    var pMatch;

    while ((pMatch = pRegex.exec(xmlText)) !== null) {
        var pAttrs = pMatch[1];
        var pBody = pMatch[2];

        var beginMatch = pAttrs.match(/begin=["']([^"']+)["']/i);
        var endMatch = pAttrs.match(/end=["']([^"']+)["']/i);

        var cleanText = decodeXmlText(pBody.replace(/<[^>]+>/g, "")).replace(/\s+/g, " ").trim();
        if (cleanText.length > 0) {
            plainLines.push(cleanText);
        }

        if (!beginMatch) continue;

        var lineStart = parseTTMLTime(beginMatch[1]);
        var lineEnd = endMatch ? parseTTMLTime(endMatch[1]) : 0;
        var lineDuration = lineEnd > lineStart ? lineEnd - lineStart : 0;

        var parts = [];
        var spanRegex = /<span\b([^>]*)>([\s\S]*?)<\/span>|([^<]+)/gi;
        var spanMatch;
        var fullText = "";
        var pendingText = "";

        while ((spanMatch = spanRegex.exec(pBody)) !== null) {
            if (spanMatch[3]) {
                var raw = decodeXmlText(spanMatch[3]);
                fullText += raw;
                if (parts.length > 0) {
                    parts[parts.length - 1].words += raw;
                } else {
                    pendingText += raw;
                }
            } else {
                var spanAttrs = spanMatch[1];
                var spanText = spanMatch[2];
                spanText = decodeXmlText(spanText.replace(/<[^>]+>/g, ""));
                if (!spanText) continue;

                var sBeginMatch = spanAttrs.match(/begin=["']([^"']+)["']/i);
                var sEndMatch = spanAttrs.match(/end=["']([^"']+)["']/i);
                var isBg = /role=["']x-bg["']/i.test(spanAttrs) || /role=["']x-bg["']/i.test(pAttrs);

                if (sBeginMatch && sEndMatch) {
                    var sStart = parseTTMLTime(sBeginMatch[1]);
                    var sEnd = parseTTMLTime(sEndMatch[1]);
                    parts.push({
                        startTimeMs: sStart,
                        durationMs: Math.max(50, sEnd - sStart),
                        words: pendingText + spanText,
                        isBackground: isBg
                    });
                    pendingText = "";
                } else if (parts.length > 0) {
                    parts[parts.length - 1].words += spanText;
                } else {
                    pendingText += spanText;
                }
                fullText += spanText;
            }
        }
        if (pendingText && parts.length > 0) {
            parts[parts.length - 1].words += pendingText;
        }

        for (var cleanPart = 0; cleanPart < parts.length; cleanPart++) {
            parts[cleanPart].words = cleanLyricText(parts[cleanPart].words, false);
        }
        var cleanFullText = cleanLyricText(fullText, true);
        if (cleanFullText.length > 0) {
            timedLines.push({
                startTimeMs: lineStart,
                durationMs: lineDuration,
                words: cleanFullText,
                parts: parts.length > 0 ? parts : [],
                isInstrumental: false,
                isUnsynced: false
            });
        }
    }

    if (timedLines.length > 0) {
        timedLines.sort(function(a, b) { return a.startTimeMs - b.startTimeMs; });
        for (var i = 0; i < timedLines.length; i++) {
            if (timedLines[i].durationMs === 0) {
                if (i + 1 < timedLines.length) {
                    timedLines[i].durationMs = Math.max(500, timedLines[i + 1].startTimeMs - timedLines[i].startTimeMs);
                } else if (songDurationMs > timedLines[i].startTimeMs) {
                    timedLines[i].durationMs = songDurationMs - timedLines[i].startTimeMs;
                } else {
                    timedLines[i].durationMs = 4000;
                }
            }
            var lineParts = timedLines[i].parts;
            if (lineParts.length > 0) {
                lineParts.sort(function(a, b) { return a.startTimeMs - b.startTimeMs; });
                for (var partIndex = 0; partIndex < lineParts.length; partIndex++) {
                    var maximumEnd = timedLines[i].startTimeMs + timedLines[i].durationMs;
                    var nextStart = partIndex + 1 < lineParts.length
                                  ? lineParts[partIndex + 1].startTimeMs : maximumEnd;
                    if (lineParts[partIndex].durationMs <= 0) {
                        lineParts[partIndex].durationMs = Math.max(50,
                            nextStart - lineParts[partIndex].startTimeMs);
                    }
                }
            }
        }
        return timedLines;
    }

    if (plainLines.length > 0) {
        var totalDur = songDurationMs > 0 ? songDurationMs : (plainLines.length * 4000);
        var step = totalDur / plainLines.length;
        var unLines = [];
        for (var j = 0; j < plainLines.length; j++) {
            unLines.push({
                startTimeMs: Math.round(j * step),
                durationMs: Math.round(step),
                words: plainLines[j],
                parts: [],
                isInstrumental: false,
                isUnsynced: true
            });
        }
        return unLines;
    }

    return [];
}

function parseLRC(text, songDurationMs) {
    if (!songDurationMs) songDurationMs = 0;
    var lines = [];
    var rawLines = text.split(/\r?\n/);
    var timeTagRegex = /\[(\d+:\d+(?:\.\d+)?)\]/g;
    var wordTagRegex = /<(\d+:\d+(?:\.\d+)?)>/g;
    var offsetMatch = text.match(/^\s*\[offset:([+-]?\d+)\]\s*$/im);
    var offsetMs = offsetMatch ? parseInt(offsetMatch[1], 10) : 0;
    if (!isFinite(offsetMs)) offsetMs = 0;

    function parseTime(t) {
        if (!t) return 0;
        var p = t.split(':');
        if (p.length === 2) {
            return Math.max(0, Math.round(parseInt(p[0], 10) * 60000 + parseFloat(p[1]) * 1000 + offsetMs));
        }
        if (p.length === 3) {
            return Math.max(0, Math.round(parseInt(p[0], 10) * 3600000 + parseInt(p[1], 10) * 60000 + parseFloat(p[2]) * 1000 + offsetMs));
        }
        return 0;
    }

    for (var l = 0; l < rawLines.length; l++) {
        var raw = rawLines[l].trim();
        if (!raw) continue;
        if (/^\[[a-zA-Z]+:/.test(raw)) continue;

        var timestamps = [];
        var match;
        while ((match = timeTagRegex.exec(raw)) !== null) {
            timestamps.push(parseTime(match[1]));
        }
        if (timestamps.length === 0) continue;

        var content = raw.replace(timeTagRegex, '').trim();
        if (!content) continue;

        var parts = [];
        if (wordTagRegex.test(content)) {
            wordTagRegex.lastIndex = 0;
            var tokens = content.split(wordTagRegex);
            for (var k = 1; k < tokens.length; k += 2) {
                var wTime = parseTime(tokens[k]);
                var wText = cleanLyricText(tokens[k + 1] || "", false);
                parts.push({
                    startTimeMs: wTime,
                    durationMs: 0,
                    words: wText,
                    isBackground: false
                });
            }
            for (var p = 0; p < parts.length; p++) {
                if (p + 1 < parts.length) {
                    parts[p].durationMs = Math.max(50, parts[p + 1].startTimeMs - parts[p].startTimeMs);
                } else {
                    parts[p].durationMs = 500;
                }
            }
        }

        var cleanWords = cleanLyricText(content.replace(wordTagRegex, ''), true);
        // LRC permits several timestamps on one line (usually a repeated
        // chorus). Preserve every occurrence instead of silently taking the
        // earliest one. Enhanced word timestamps are shifted with the clone.
        var referenceStart = Math.min.apply(null, timestamps);
        for (var stamp = 0; stamp < timestamps.length; stamp++) {
            var delta = timestamps[stamp] - referenceStart;
            var clonedParts = [];
            for (var partIndex = 0; partIndex < parts.length; partIndex++) {
                clonedParts.push({
                    startTimeMs: Math.max(0, parts[partIndex].startTimeMs + delta),
                    durationMs: parts[partIndex].durationMs,
                    words: parts[partIndex].words,
                    isBackground: parts[partIndex].isBackground
                });
            }
            lines.push({
                startTimeMs: timestamps[stamp],
                durationMs: 0,
                words: cleanWords,
                parts: clonedParts,
                isInstrumental: false,
                isUnsynced: false
            });
        }
    }

    if (lines.length === 0) {
        return parsePlainLyrics(text, songDurationMs);
    }

    lines.sort(function(a, b) { return a.startTimeMs - b.startTimeMs; });

    for (var i = 0; i < lines.length; i++) {
        if (i + 1 < lines.length) {
            lines[i].durationMs = Math.max(500, lines[i + 1].startTimeMs - lines[i].startTimeMs);
        } else if (songDurationMs > lines[i].startTimeMs) {
            lines[i].durationMs = songDurationMs - lines[i].startTimeMs;
        } else {
            lines[i].durationMs = 4000;
        }
        if (lines[i].parts.length > 0) {
            var lastPart = lines[i].parts[lines[i].parts.length - 1];
            var partElapsed = lastPart.startTimeMs - lines[i].startTimeMs;
            lastPart.durationMs = Math.max(200, lines[i].durationMs - partElapsed);
        }
    }

    return lines;
}

function insertInstrumentals(lines, totalDurationMs, gapThresholdMs) {
    if (!gapThresholdMs) gapThresholdMs = 5000;
    if (!lines || lines.length === 0) return lines;
    if (lines[0].isUnsynced) return lines;

    var result = [];
    var makeBreak = function(start, dur) {
        return {
            startTimeMs: start,
            durationMs: dur,
            words: "•••",
            parts: [],
            isInstrumental: true,
            isUnsynced: false
        };
    };

    if (lines[0].startTimeMs > gapThresholdMs) {
        result.push(makeBreak(0, lines[0].startTimeMs));
    }

    for (var i = 0; i < lines.length; i++) {
        result.push(lines[i]);
        if (i < lines.length - 1) {
            var endCurrent = lines[i].startTimeMs + lines[i].durationMs;
            var gap = lines[i + 1].startTimeMs - endCurrent;
            if (gap > gapThresholdMs) {
                result.push(makeBreak(endCurrent, gap));
            }
        }
    }

    if (totalDurationMs > 0) {
        var last = lines[lines.length - 1];
        var lastEnd = last.startTimeMs + last.durationMs;
        var remaining = totalDurationMs - lastEnd;
        if (remaining > gapThresholdMs) {
            result.push(makeBreak(lastEnd, remaining));
        }
    }

    return result;
}

function httpGet(url, callback) {
    var xhr = new XMLHttpRequest();
    var completed = false;

    function finish(error, responseText, status) {
        if (completed) return;
        completed = true;
        callback(error, responseText, status);
    }

    xhr.open("GET", url, true);
    xhr.setRequestHeader("User-Agent", "BetterLyrics-Plasma/1.0");
    xhr.timeout = 7000;
    xhr.onreadystatechange = function() {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status >= 200 && xhr.status < 300) {
                finish(null, xhr.responseText, xhr.status);
            } else {
                finish(new Error("HTTP status " + xhr.status), null, xhr.status);
            }
        }
    };
    xhr.ontimeout = function() {
        finish(new Error("Timeout"), null, 0);
    };
    xhr.onerror = function() {
        finish(new Error("Network error"), null, 0);
    };
    xhr.onabort = function() {
        finish(new Error("Request aborted"), null, 0);
    };
    xhr.send();
}

function httpPostJson(url, value, callback) {
    var xhr = new XMLHttpRequest();
    var completed = false;
    function finish(error, responseText) {
        if (completed) return;
        completed = true;
        callback(error, responseText);
    }
    xhr.open("POST", url, true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("User-Agent", "BetterLyrics-Plasma/1.0");
    xhr.timeout = 7000;
    xhr.onreadystatechange = function() {
        if (xhr.readyState !== XMLHttpRequest.DONE) return;
        if (xhr.status >= 200 && xhr.status < 300) finish(null, xhr.responseText);
        else finish(new Error("HTTP status " + xhr.status), null);
    };
    xhr.ontimeout = function() { finish(new Error("Timeout"), null); };
    xhr.onerror = function() { finish(new Error("Network error"), null); };
    xhr.onabort = function() { finish(new Error("Request aborted"), null); };
    xhr.send(JSON.stringify(value));
}

function containsNonLatin(value) {
    // Scripts for which a Latin reading is useful. Latin punctuation, emoji,
    // and musical symbols alone must not trigger a translation request.
    return /[\u0370-\u052f\u0600-\u06ff\u0750-\u077f\u0900-\u0dff\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]/.test(value || "");
}

function applyRomanizations(result, candidates, values) {
    var changed = false;
    for (var i = 0; i < candidates.length; i++) {
        var romanized = values[i] ? values[i].trim() : "";
        var original = candidates[i].text.trim();
        if (romanized && romanized.toLowerCase() !== original.toLowerCase()) {
            result.lines[candidates[i].index].romanization = romanized;
            changed = true;
        }
    }
    return changed;
}

function romanizeWithGoogle(result, candidates, done) {
    if (candidates.length === 0) { done(false); return; }
    var separator = "\n\n;\n\n";
    var combined = candidates.map(function(item) { return item.text; }).join(separator);
    var url = "https://translate.googleapis.com/translate_a/single?client=gtx"
            + "&sl=auto&tl=auto-Latn&dt=t&dt=rm&q=" + encodeURIComponent(combined);
    // Avoid an oversized GET. Splitting by count also makes a malformed
    // response affect a small group rather than a whole song.
    if (url.length > 12000 && candidates.length > 1) {
        var middle = Math.ceil(candidates.length / 2);
        var anyChanged = false;
        romanizeWithGoogle(result, candidates.slice(0, middle), function(firstChanged) {
            anyChanged = anyChanged || firstChanged;
            romanizeWithGoogle(result, candidates.slice(middle), function(secondChanged) {
                done(anyChanged || secondChanged);
            });
        });
        return;
    }
    httpGet(url, function(error, response) {
        if (error || !response) { done(false); return; }
        try {
            var data = JSON.parse(response);
            var full = "";
            var chunks = data && data[0] ? data[0] : [];
            for (var i = 0; i < chunks.length; i++) {
                if (chunks[i]) full += chunks[i][3] || chunks[i][2] || "";
            }
            var values = full.split(separator);
            if (values.length !== candidates.length) {
                var semicolon = full.split(";").filter(function(value) { return value.trim(); });
                if (semicolon.length === candidates.length) values = semicolon;
            }
            done(values.length === candidates.length
                 ? applyRomanizations(result, candidates, values) : false);
        } catch (parseError) { done(false); }
    });
}

function enrichRomanization(result, videoId, callback) {
    if (!result || !result.lines) return;
    var candidates = [];
    for (var i = 0; i < result.lines.length; i++) {
        var line = result.lines[i];
        if (line && !line.isInstrumental && !line.romanization && containsNonLatin(line.words)) {
            candidates.push({ index: i, text: line.words });
        }
    }
    if (candidates.length === 0) return;

    httpPostJson("https://unison.betterlyrics.org/translate", {
        lines: candidates.map(function(item) { return item.text; }),
        to: "en",
        videoId: videoId || undefined
    }, function(error, response) {
        var unresolved = candidates;
        var changed = false;
        if (!error && response) {
            try {
                var data = JSON.parse(response);
                if (data && Array.isArray(data.lines) && data.lines.length === candidates.length) {
                    var values = data.lines.map(function(line) { return line ? line.romanization : ""; });
                    changed = applyRomanizations(result, candidates, values);
                    unresolved = candidates.filter(function(item) {
                        return !result.lines[item.index].romanization;
                    });
                }
            } catch (parseError) {}
        }
        romanizeWithGoogle(result, unresolved, function(googleChanged) {
            if (changed || googleChanged) callback(null, result);
        });
    });
}

function cleanTitle(title) {
    if (!title) return "";
    return title
        .replace(/\s*\|\s*YouTube Music$/i, '')
        .replace(/\s*\((Official\s+)?(Music\s+)?(Video|Audio|Lyric\s+Video|Visualizer)\)/gi, '')
        .replace(/\s*\[(Official\s+)?(Music\s+)?(Video|Audio|Lyric\s+Video|Visualizer)\]/gi, '')
        .trim();
}

function stripFeat(title) {
    if (!title) return "";
    return title
        .replace(/\s*[\(\[](feat|ft)\.?\s+[^\)\]]+[\)\]]/gi, '')
        .replace(/\s+(feat|ft)\.?\s+.*$/i, '')
        .trim();
}

function cleanArtist(artist) {
    if (!artist) return "";
    return artist
        .replace(/\s*-\s*Topic$/i, '')
        .trim();
}

function normalizeArtistPunctuation(artist) {
    if (!artist) return "";
    return artist.replace(/[·•]/g, ' ').replace(/\s+/g, ' ').trim();
}

function extractVideoId(url) {
    if (!url) return "";
    var match = url.match(/(?:[?&]v=|youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:embed|shorts|live)\/)([a-zA-Z0-9_-]{11})(?:[^a-zA-Z0-9_-]|$)/i);
    return match ? match[1] : "";
}

function normalizeForMatch(value) {
    return (value || "").toLowerCase()
        .replace(/[\s\-_,./#!$%^&*;:{}=`~()\[\]"'|<>?]+/g, " ")
        .replace(/^\s+|\s+$/g, "");
}

function chooseBestSearchResult(results, title, artist, durationSeconds, requireSynced) {
    if (!Array.isArray(results)) return null;
    var wantedTitle = normalizeForMatch(title);
    var wantedArtist = normalizeForMatch(artist);
    var best = null;
    var bestScore = -999999;
    for (var i = 0; i < results.length; i++) {
        var item = results[i];
        if (!item || (requireSynced && !item.syncedLyrics)) continue;
        if (!requireSynced && !item.plainLyrics) continue;
        var itemTitle = normalizeForMatch(item.trackName || item.name || "");
        var itemArtist = normalizeForMatch(item.artistName || "");
        var score = 0;
        if (wantedTitle && itemTitle === wantedTitle) score += 80;
        else if (wantedTitle && (itemTitle.indexOf(wantedTitle) >= 0 || wantedTitle.indexOf(itemTitle) >= 0)) score += 30;
        if (wantedArtist && itemArtist === wantedArtist) score += 50;
        else if (wantedArtist && (itemArtist.indexOf(wantedArtist) >= 0 || wantedArtist.indexOf(itemArtist) >= 0)) score += 20;
        var itemDuration = Number(item.duration || 0);
        if (durationSeconds > 0 && itemDuration > 0) {
            var difference = Math.abs(itemDuration - durationSeconds);
            score += Math.max(-50, 35 - difference * 3);
        }
        if (score > bestScore) {
            best = item;
            bestScore = score;
        }
    }
    return best;
}

/**
 * Main fetch function:
 * tries Unison -> BiniLyrics -> LRCLIB with fallback to plain lyrics
 */
function fetchLyrics(track, artist, album, durationSeconds, videoUrl, enableRomanization, callback) {
    var rawTitle = cleanTitle(track);
    var strippedTitle = stripFeat(rawTitle);
    var rawArtist = cleanArtist(artist);
    var normArtist = normalizeArtistPunctuation(rawArtist);
    var alb = album ? album.trim() : "";
    var durSec = Math.round(durationSeconds || 0);
    var durMs = durSec * 1000;
    var videoId = extractVideoId(videoUrl);

    var cacheKey = (rawTitle + "---" + rawArtist + "---" + durSec).toLowerCase();
    var cached = getCachedLyrics(cacheKey);
    if (cached) {
        console.info("[BetterLyrics] Serving from in-memory cache:", cacheKey);
        callback(null, cached);
        if (enableRomanization) enrichRomanization(cached, videoId, callback);
        return;
    }

    console.info("[BetterLyrics] Fetching lyrics for:", rawTitle, "by", rawArtist, "duration:", durSec, "videoId:", videoId);

    // Track any unsynced plain lyrics found as a fallback if no synced lyrics exist
    var fallbackPlainResult = null;

    function savePlainFallback(sourceName, plainLines) {
        if (!fallbackPlainResult && plainLines && plainLines.length > 0) {
            fallbackPlainResult = {
                source: sourceName,
                syncType: "none",
                lines: plainLines
            };
        }
    }

    // Helper to finish with synced lyrics
    function finishWithLyrics(sourceName, parsedLines, isSyllable) {
        if (parsedLines && parsedLines.length > 0) {
            if (parsedLines[0].isUnsynced) {
                savePlainFallback(sourceName, parsedLines);
                return false;
            }
            var withBreaks = insertInstrumentals(parsedLines, durMs);
            var result = {
                source: sourceName,
                syncType: isSyllable ? "syllable" : "line",
                lines: withBreaks
            };
            cacheLyrics(cacheKey, result);
            console.info("[BetterLyrics] Success from " + sourceName + "! Lines:", withBreaks.length, "syllable:", isSyllable);
            callback(null, result);
            if (enableRomanization) enrichRomanization(result, videoId, callback);
            return true;
        }
        return false;
    }

    // Helper to finish with plain lyrics when cascade finishes without synced lyrics
    function finishCascade() {
        if (fallbackPlainResult && fallbackPlainResult.lines.length > 0) {
            cacheLyrics(cacheKey, fallbackPlainResult);
            console.info("[BetterLyrics] Using plain/unsynced fallback from " + fallbackPlainResult.source + "! Lines:", fallbackPlainResult.lines.length);
            callback(null, fallbackPlainResult);
            if (enableRomanization) enrichRomanization(fallbackPlainResult, videoId, callback);
            return;
        }
        console.info("[BetterLyrics] No lyrics found after all fallback providers.");
        callback(new Error("No lyrics found"), null);
    }

    // 1. Unison
    function stepUnison() {
        if (!videoId) {
            stepBiniLyrics1();
            return;
        }

        var uUrl = "https://unison.betterlyrics.org/lyrics?v=" + encodeURIComponent(videoId) +
                   "&song=" + encodeURIComponent(rawTitle) +
                   "&artist=" + encodeURIComponent(rawArtist) +
                   "&duration=" + durSec;

        httpGet(uUrl, function(err, resp) {
            if (!err && resp) {
                try {
                    var data = JSON.parse(resp);
                    var payload = data.data || data;
                    if (payload && payload.lyrics) {
                        var parsed = [];
                        var isSyllable = false;
                        if (payload.format === "ttml" || payload.lyrics.indexOf("<tt") !== -1) {
                            parsed = parseTTML(payload.lyrics, durMs);
                            isSyllable = parsed.some(function(line) { return line.parts && line.parts.length > 0; });
                        } else {
                            parsed = parseLRC(payload.lyrics, durMs);
                            isSyllable = payload.syncType === "richsync" || parsed.some(function(line) { return line.parts && line.parts.length > 0; });
                        }
                        if (finishWithLyrics("Unison", parsed, isSyllable)) return;
                    }
                } catch(e) {}
            }
            stepBiniLyrics1();
        });
    }

    // 2. BiniLyrics with full metadata
    function stepBiniLyrics1() {
        if (!durSec) {
            stepLrclibGet();
            return;
        }

        var bUrl = "https://lyrics-api.binimum.org/?track=" + encodeURIComponent(rawTitle) +
                   "&artist=" + encodeURIComponent(rawArtist) +
                   (alb ? "&album=" + encodeURIComponent(alb) : "") +
                   "&duration=" + durSec;

        httpGet(bUrl, function(err, resp) {
            if (!err && resp) {
                try {
                    var bData = JSON.parse(resp);
                    if (bData && bData.results && bData.results.length > 0 && bData.results[0].lyricsUrl) {
                        httpGet(bData.results[0].lyricsUrl, function(ttmlErr, ttmlResp) {
                            if (!ttmlErr && ttmlResp) {
                                var lines = parseTTML(ttmlResp, durMs);
                                var isSyllable = lines.some(function(line) { return line.parts && line.parts.length > 0; });
                                if (finishWithLyrics("BiniLyrics", lines, isSyllable)) return;
                            }
                            stepBiniLyrics2();
                        });
                        return;
                    }
                } catch(e) {}
            }
            stepBiniLyrics2();
        });
    }

    // 3. BiniLyrics without album or with stripped title / normalized artist
    function stepBiniLyrics2() {
        var tToUse = strippedTitle !== rawTitle ? strippedTitle : rawTitle;
        var aToUse = normArtist !== rawArtist ? normArtist : rawArtist;

        var bUrl = "https://lyrics-api.binimum.org/?track=" + encodeURIComponent(tToUse) +
                   "&artist=" + encodeURIComponent(aToUse);

        httpGet(bUrl, function(err, resp) {
            if (!err && resp) {
                try {
                    var bData = JSON.parse(resp);
                    if (bData && bData.results && bData.results.length > 0 && bData.results[0].lyricsUrl) {
                        httpGet(bData.results[0].lyricsUrl, function(ttmlErr, ttmlResp) {
                            if (!ttmlErr && ttmlResp) {
                                var lines = parseTTML(ttmlResp, durMs);
                                var isSyllable = lines.some(function(line) { return line.parts && line.parts.length > 0; });
                                if (finishWithLyrics("BiniLyrics", lines, isSyllable)) return;
                            }
                            stepLrclibGet();
                        });
                        return;
                    }
                } catch(e) {}
            }
            stepLrclibGet();
        });
    }

    // 4. LRCLIB exact get
    function stepLrclibGet() {
        var lUrl = "https://lrclib.net/api/get?track_name=" + encodeURIComponent(rawTitle) +
                   "&artist_name=" + encodeURIComponent(rawArtist) +
                   (alb ? "&album_name=" + encodeURIComponent(alb) : "") +
                   (durSec ? "&duration=" + durSec : "");

        httpGet(lUrl, function(err, resp) {
            if (!err && resp) {
                try {
                    var lData = JSON.parse(resp);
                    if (lData) {
                        if (lData.syncedLyrics) {
                            var lines = parseLRC(lData.syncedLyrics, durMs);
                            var isSyllable = lines.some(function(line) { return line.parts && line.parts.length > 0; });
                            if (finishWithLyrics("LRCLIB", lines, isSyllable)) return;
                        } else if (lData.plainLyrics) {
                            savePlainFallback("LRCLIB", parsePlainLyrics(lData.plainLyrics, durMs));
                        }
                    }
                } catch(e) {}
            }
            stepLrclibSearch1();
        });
    }

    // 5. LRCLIB search with track and artist
    function stepLrclibSearch1() {
        var sUrl = "https://lrclib.net/api/search?track_name=" + encodeURIComponent(strippedTitle || rawTitle) +
                   "&artist_name=" + encodeURIComponent(normArtist || rawArtist);

        httpGet(sUrl, function(err, resp) {
            if (!err && resp) {
                try {
                    var sData = JSON.parse(resp);
                    if (Array.isArray(sData)) {
                        var foundSynced = chooseBestSearchResult(sData, strippedTitle || rawTitle,
                                                                 normArtist || rawArtist, durSec, true);
                        if (foundSynced) {
                            var lines = parseLRC(foundSynced.syncedLyrics, durMs);
                            var isSyllable = lines.some(function(line) { return line.parts && line.parts.length > 0; });
                            if (finishWithLyrics("LRCLIB (Search)", lines, isSyllable)) return;
                        }
                        var foundPlain = chooseBestSearchResult(sData, strippedTitle || rawTitle,
                                                                normArtist || rawArtist, durSec, false);
                        if (foundPlain) {
                            savePlainFallback("LRCLIB (Search)", parsePlainLyrics(foundPlain.plainLyrics, durMs));
                        }
                    }
                } catch(e) {}
            }
            stepLrclibSearch2();
        });
    }

    // 6. LRCLIB general search with query q
    function stepLrclibSearch2() {
        var q = (strippedTitle || rawTitle) + " " + (normArtist || rawArtist);
        var sUrl = "https://lrclib.net/api/search?q=" + encodeURIComponent(q);

        httpGet(sUrl, function(err, resp) {
            if (!err && resp) {
                try {
                    var sData = JSON.parse(resp);
                    if (Array.isArray(sData)) {
                        var foundSynced = chooseBestSearchResult(sData, strippedTitle || rawTitle,
                                                                 normArtist || rawArtist, durSec, true);
                        if (foundSynced) {
                            var lines = parseLRC(foundSynced.syncedLyrics, durMs);
                            var isSyllable = lines.some(function(line) { return line.parts && line.parts.length > 0; });
                            if (finishWithLyrics("LRCLIB (General)", lines, isSyllable)) return;
                        }
                        var foundPlain = chooseBestSearchResult(sData, strippedTitle || rawTitle,
                                                                normArtist || rawArtist, durSec, false);
                        if (foundPlain) {
                            savePlainFallback("LRCLIB (General)", parsePlainLyrics(foundPlain.plainLyrics, durMs));
                        }
                    }
                } catch(e) {}
            }
            finishCascade();
        });
    }

    // Kick off cascade
    stepUnison();
}
