// Pure voice helpers shared by the browser component and the Node tests (tests/js/test_voice_logic.js).
// No DOM access here: every function takes plain values and returns plain values.
(function (root) {
  "use strict";

  const STOP_LISTEN = /^(stop listening|stop hands[- ]?free|hands[- ]?free off|that'?s all|sunna band karo|sunna band|sambhadvanu bandh karo|सुनना बंद करो|સાંભળવાનું બંધ કરો)\b/i;
  // Short phrases that interrupt the assistant while it is speaking (barge-in).
  const STOP_TALK = /^(stop|wait|enough|quiet|be quiet|shut up|ok stop|okay stop|bas|bas karo|ruko|ruk jao|chup|chup karo|rehne do|thobho|bas kar|बस|रुको|चुप|ठहरो|બસ|થોભો|ચૂપ|રહેવા દો)[\s.!]*$/i;

  function normalize(text) {
    return String(text || "").toLowerCase().replace(/[.,!?;:"'()\-]/g, " ").replace(/\s+/g, " ").trim();
  }

  // Wake word at the start of a phrase. Returns {matched, rest}. Tolerates "hey"/"ok" before it and small
  // spelling differences of the recogniser (adhyaksh, adhyaksha, adyaksh, adhyax).
  function matchWake(text, words) {
    const t = String(text || "").trim();
    const list = (words || []).map(normalize).filter(Boolean);
    const lead = /^(?:hey|hi|ok|okay|hello|oye|are)\s+/i;
    let body = t.replace(lead, "");
    const low = normalize(body);
    for (let i = 0; i < list.length; i++) {
      const w = list[i];
      if (low === w || low.indexOf(w + " ") === 0) {
        const n = w.split(" ").length;
        const rest = body.split(/\s+/).slice(n).join(" ").replace(/^[\s,.:!-]+/, "");
        return { matched: true, rest: rest };
      }
    }
    const first = low.split(" ")[0] || "";
    if (/^adh?y[aeiou]?k?(?:sh|s|x|ch)a?$/.test(first) || first === "अध्यक्ष" || first === "અધ્યક્ષ") {
      return { matched: true, rest: body.split(/\s+/).slice(1).join(" ").replace(/^[\s,.:!-]+/, "") };
    }
    return { matched: false, rest: t };
  }

  function isStopListen(text) { return STOP_LISTEN.test(String(text || "").trim()); }
  function isStopTalking(text) { return STOP_TALK.test(String(text || "").trim()); }

  // True when what the microphone heard is (mostly) the assistant's own voice coming back from the speakers.
  function isEcho(heard, spoken) {
    const h = normalize(heard).split(" ").filter(function (w) { return w.length > 1; });
    if (!h.length) return true;
    const s = new Set(normalize(spoken).split(" "));
    let hit = 0;
    h.forEach(function (w) { if (s.has(w)) hit += 1; });
    return hit / h.length >= 0.5;
  }

  // Barge-in decision while the assistant speaks: "stop" (stop speaking), "command" (stop and handle the
  // phrase as a new request), or "ignore" (echo or too short).
  function bargeDecision(heard, spoken) {
    if (isStopTalking(heard) || isStopListen(heard)) return "stop";
    const words = normalize(heard).split(" ").filter(Boolean);
    if (words.length < 2 || isEcho(heard, spoken)) return "ignore";
    return "command";
  }

  // Split a reply into short sentences so long replies are spoken reliably (Chrome stops very long utterances).
  function splitForSpeech(text, maxLen) {
    const max = maxLen || 180;
    const parts = String(text || "").replace(/\s+/g, " ").trim().split(/(?<=[.!?।])\s+/);
    const out = [];
    parts.forEach(function (p) {
      while (p.length > max) {
        let cut = p.lastIndexOf(", ", max);
        if (cut < max / 2) cut = p.lastIndexOf(" ", max);
        if (cut <= 0) cut = max;
        out.push(p.slice(0, cut + 1).trim());
        p = p.slice(cut + 1).trim();
      }
      if (p) out.push(p);
    });
    return out;
  }

  // Best voice for a language: the user's chosen name, then high-quality voices (Natural, Neural, Online,
  // Google), then any voice of that language and region, then any voice of that language.
  function pickVoice(voices, lang, preferred) {
    const list = voices || [];
    if (preferred) {
      const p = list.find(function (v) { return v.name === preferred; });
      if (p) return p;
    }
    const code = String(lang || "en-IN").toLowerCase();
    const base = code.slice(0, 2);
    const same = list.filter(function (v) { return String(v.lang).toLowerCase().replace("_", "-") === code; });
    const family = list.filter(function (v) { return String(v.lang).toLowerCase().indexOf(base) === 0; });
    const good = /natural|neural|online|google|premium|enhanced/i;
    return same.find(function (v) { return good.test(v.name); }) || family.find(function (v) { return good.test(v.name); }) ||
           same[0] || family[0] || null;
  }

  // Voice activity detection on per-frame loudness (RMS). push(rms, nowMs) returns "start", "end", "cancel" or "".
  function createVad(opts) {
    const o = Object.assign({ threshold: 0.02, silenceMs: 800, minMs: 300, maxMs: 15000, holdMs: 120 }, opts || {});
    let inSpeech = false, startAt = 0, lastLoud = 0, loudSince = 0;
    return {
      push: function (rms, now) {
        if (!inSpeech) {
          if (rms >= o.threshold) {
            if (!loudSince) loudSince = now;
            if (now - loudSince >= o.holdMs) { inSpeech = true; startAt = loudSince; lastLoud = now; return "start"; }
          } else loudSince = 0;
          return "";
        }
        if (rms >= o.threshold) lastLoud = now;
        if (now - startAt >= o.maxMs) { inSpeech = false; loudSince = 0; return "end"; }
        if (now - lastLoud >= o.silenceMs) {
          inSpeech = false; loudSince = 0;
          return (lastLoud - startAt >= o.minMs) ? "end" : "cancel";
        }
        return "";
      },
      active: function () { return inSpeech; },
      reset: function () { inSpeech = false; loudSince = 0; }
    };
  }

  function rms(samples) {
    let s = 0;
    for (let i = 0; i < samples.length; i++) s += samples[i] * samples[i];
    return samples.length ? Math.sqrt(s / samples.length) : 0;
  }

  // Float32 samples at any rate -> 16 kHz mono 16-bit PCM WAV bytes (Uint8Array).
  function encodeWav16k(samples, inRate) {
    const ratio = inRate / 16000;
    const n = Math.max(0, Math.floor(samples.length / ratio));
    const buf = new ArrayBuffer(44 + n * 2);
    const v = new DataView(buf);
    function str(off, s) { for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i)); }
    str(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); str(8, "WAVE"); str(12, "fmt ");
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 16000, true);
    v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, "data"); v.setUint32(40, n * 2, true);
    for (let i = 0; i < n; i++) {
      const x = Math.max(-1, Math.min(1, samples[Math.floor(i * ratio)] || 0));
      v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true);
    }
    return new Uint8Array(buf);
  }

  function toBase64(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return (typeof btoa === "function") ? btoa(s) : Buffer.from(s, "binary").toString("base64");
  }

  const api = { STOP_LISTEN: STOP_LISTEN, matchWake: matchWake, isStopListen: isStopListen, isStopTalking: isStopTalking,
                isEcho: isEcho, bargeDecision: bargeDecision, splitForSpeech: splitForSpeech, pickVoice: pickVoice,
                createVad: createVad, rms: rms, encodeWav16k: encodeWav16k, toBase64: toBase64 };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.VoiceLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
