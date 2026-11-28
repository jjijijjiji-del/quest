"""문장 듣고 시간·숫자 고르기: 문장 소리 만들기 (GitHub Actions에서 실행)
Supertonic F1 (앱 음성 팩과 같은 목소리), 보통 0.75배(_d) · 천천히 0.7배(_s)
만든 소리를 받아 적기(whisper)로 다시 들어 보고, 정답 부분이 안 들리면 설정을 바꿔 다시 만듦 → report.json"""
import json, os, re, sys, subprocess
import numpy as np, soundfile as sf
from supertonic import TTS
from faster_whisper import WhisperModel
src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
items = json.load(open(src, encoding="utf-8"))
tts = TTS(auto_download=True); sr = getattr(tts, "sample_rate", None) or 44100
style = tts.get_voice_style(voice_name="F1")
asr = WhisperModel("small", device="cpu", compute_type="int8")
SN = "영일이삼사오육칠팔구"
def norm(t):
    t = re.sub(r"[^가-힣0-9]", "", t)
    return t
def synth(text, sp, steps):
    w, _ = tts.synthesize(text, voice_style=style, lang="ko", total_steps=steps, speed=sp, silence_duration=0.15)
    w = np.asarray(w, dtype=np.float32).reshape(-1); a = np.abs(w)
    idx = np.where(a > 0.01 * max(a.max(), 1e-6))[0]
    if len(idx): w = w[max(0, idx[0] - int(sr * .03)): min(len(w), idx[-1] + int(sr * .12))]
    return w
def hear(w):
    n = int(len(w) * 16000 / sr); x = np.interp(np.linspace(0, len(w) - 1, n), np.arange(len(w)), w).astype(np.float32)
    segs, _ = asr.transcribe(x, language="ko", beam_size=3, vad_filter=False, condition_on_previous_text=False,
                             initial_prompt="숫자는 한글로 적어요. 세 시, 오 분, 삼 층.")
    return " ".join(s.text for s in segs).strip()
def ok(heard, it):
    h = norm(heard); a = norm(it["ans_say"]); d = norm(it["ans"])
    return a in h or d in h
report = []
for it in items:
    rec = {"id": it["id"], "say": it["say"]}
    for tag, sp in (("d", 0.75), ("s", 0.70)):
        best = None
        for steps in (10, 12, 8, 14):
            w = synth(it["say"], sp, steps); heard = hear(w); good = ok(heard, it)
            if best is None or good: best = (w, heard, good, steps)
            if good: break
        w, heard, good, steps = best
        sf.write(f"/tmp/tq.wav", w, sr)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", "/tmp/tq.wav", "-ac", "1", "-ar", "24000", "-c:a", "libopus", "-b:a", "32k", f"{out}/{it['id']}_{tag}.ogg"], check=True)
        rec[tag] = {"heard": heard, "ok": good, "steps": steps, "sec": round(len(w) / sr, 2)}
    report.append(rec); print(it["id"], rec["d"]["ok"], rec["d"]["heard"], flush=True)
json.dump(report, open(f"{out}/report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("::notice::정답 부분이 받아 적기에서 안 들린 문장:", [r["id"] for r in report if not r["d"]["ok"]])
