// Node tests for adhyaksh/voice/component/voice_logic.js. Run: node tests/js/test_voice_logic.js
const assert = require("assert");
const path = require("path");
const VL = require(path.join(__dirname, "..", "..", "adhyaksh", "voice", "component", "voice_logic.js"));
let n = 0;
function t(name, fn) { fn(); n += 1; }

t("wake word", () => {
  const w = ["adhyaksh", "hey assistant"];
  assert.deepStrictEqual(VL.matchWake("Adhyaksh open notepad", w), { matched: true, rest: "open notepad" });
  assert.deepStrictEqual(VL.matchWake("hey Adhyaksh, what time is it", w), { matched: true, rest: "what time is it" });
  assert.strictEqual(VL.matchWake("adyaksh take a screenshot", w).matched, true);   // recogniser spelling slip
  assert.strictEqual(VL.matchWake("adhyax stop", w).rest, "stop");
  assert.strictEqual(VL.matchWake("अध्यक्ष नोटपैड खोलो", w).rest, "नोटपैड खोलो");
  assert.strictEqual(VL.matchWake("open notepad adhyaksh", w).matched, false);     // must open the phrase
  assert.strictEqual(VL.matchWake("adhyaksh", w).rest, "");
});

t("barge-in decisions", () => {
  const spoken = "The capital of France is Paris. It is also the largest city.";
  assert.strictEqual(VL.bargeDecision("stop", spoken), "stop");
  assert.strictEqual(VL.bargeDecision("ruko", spoken), "stop");
  assert.strictEqual(VL.bargeDecision("बस", spoken), "stop");
  assert.strictEqual(VL.bargeDecision("the capital of france is paris", spoken), "ignore"); // our own voice
  assert.strictEqual(VL.bargeDecision("open notepad please", spoken), "command");
  assert.strictEqual(VL.bargeDecision("hmm", spoken), "ignore");
  assert.strictEqual(VL.isStopListen("stop listening"), true);
});

t("speech chunks", () => {
  const long = "First sentence here. " + "word ".repeat(80) + "end. Last one!";
  const parts = VL.splitForSpeech(long, 180);
  assert.ok(parts.length >= 3 && parts.every(p => p.length <= 181), JSON.stringify(parts));
  assert.deepStrictEqual(VL.splitForSpeech("नमस्ते। आप कैसे हैं?"), ["नमस्ते।", "आप कैसे हैं?"]);
});

t("voice choice", () => {
  const voices = [{ name: "Microsoft Ravi - English (India)", lang: "en-IN" }, { name: "Microsoft Neerja Online (Natural) - English (India)", lang: "en-IN" },
                  { name: "Google हिन्दी", lang: "hi-IN" }, { name: "Microsoft Zira", lang: "en-US" }];
  assert.strictEqual(VL.pickVoice(voices, "en-IN", "").name, "Microsoft Neerja Online (Natural) - English (India)");
  assert.strictEqual(VL.pickVoice(voices, "en-IN", "Microsoft Ravi - English (India)").name, "Microsoft Ravi - English (India)");
  assert.strictEqual(VL.pickVoice(voices, "hi-IN", "").name, "Google हिन्दी");
  assert.strictEqual(VL.pickVoice(voices, "gu-IN", ""), null);
});

t("voice activity detection", () => {
  const v = VL.createVad({ threshold: 0.02, silenceMs: 800, minMs: 300, holdMs: 100 });
  const ev = [];
  for (let ms = 0; ms <= 3000; ms += 50) {
    const loud = ms >= 500 && ms < 1500;
    const e = v.push(loud ? 0.1 : 0.001, ms);
    if (e) ev.push([e, ms]);
  }
  assert.deepStrictEqual(ev, [["start", 600], ["end", 2250]]);
  const v2 = VL.createVad({ threshold: 0.02, holdMs: 100 });  // a short click is cancelled
  const ev2 = [];
  for (let ms = 0; ms <= 2000; ms += 50) { const e = v2.push(ms >= 500 && ms < 700 ? 0.1 : 0, ms); if (e) ev2.push(e); }
  assert.deepStrictEqual(ev2, ["start", "cancel"]);
});

t("wav encoding", () => {
  const s = new Float32Array(48000).map((_, i) => Math.sin(i / 10) * 0.5);
  const wav = VL.encodeWav16k(s, 48000);
  const dv = new DataView(wav.buffer);
  assert.strictEqual(String.fromCharCode(...wav.slice(0, 4)), "RIFF");
  assert.strictEqual(dv.getUint32(24, true), 16000);
  assert.strictEqual(dv.getUint32(40, true), 16000 * 2);   // one second, 16-bit
  assert.ok(VL.toBase64(wav).startsWith("UklGR"));
  assert.ok(Math.abs(VL.rms(new Float32Array([0.5, -0.5])) - 0.5) < 1e-9);
});

console.log(`voice_logic: ${n} groups passed`);
