"""Supertonic / MeloTTS 한국어 샘플 만들기 (GitHub Actions에서 실행)

목소리마다 파일 하나: 아래 문장들을 차례로 읽고, 마지막에는 조각을 이어 붙인 버전도 들려줌.
"""
import sys, os, numpy as np, soundfile as sf

OUT = "samples"
os.makedirs(OUT, exist_ok=True)

SENTENCES = [
    "구천팔백십 원",
    "삼천오십 원",
    "사백만 오백 원",
    "십이만 팔천 원",
    "커피는 사천 원이고, 빵은 이천 원이에요. 빵은 얼마예요?",
    "칠 곱하기 팔",
]
# 앱에서처럼 조각을 따로 만들어 이어 붙인 것 (9,810원 / 커피는 4,000원이에요)
PIECES = [["구천", "팔백", "십", "원"], ["커피는", "사천", "원이에요"]]


def gap(sr, sec):
    return np.zeros(int(sr * sec), dtype=np.float32)


def trim(w, sr, th=0.01):
    a = np.abs(w)
    idx = np.where(a > th * max(a.max(), 1e-6))[0]
    if len(idx) == 0:
        return w
    s, e = max(0, idx[0] - int(sr * .02)), min(len(w), idx[-1] + int(sr * .05))
    return w[s:e]


def build(say, sr, name):
    parts = []
    for t in SENTENCES:
        parts += [say(t), gap(sr, 1.0)]
    parts.append(gap(sr, 0.6))
    for ps in PIECES:
        for p in ps:
            parts += [trim(say(p), sr), gap(sr, 0.03)]
        parts.append(gap(sr, 1.0))
    w = np.concatenate([p.astype(np.float32).reshape(-1) for p in parts])
    w = w / max(np.abs(w).max(), 1e-6) * 0.9
    sf.write(f"{OUT}/{name}.wav", w, sr)
    print("wrote", name, len(w) / sr, "sec")


def supertonic():
    from supertonic import TTS
    tts = TTS(auto_download=True)
    sr = getattr(tts, "sample_rate", None) or 44100
    for v in ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]:
        style = tts.get_voice_style(voice_name=v)

        def say(t, style=style):
            w, _ = tts.synthesize(t, voice_style=style, lang="ko", total_steps=10, speed=0.95, silence_duration=0.1)
            return np.asarray(w, dtype=np.float32).reshape(-1)

        build(say, sr, f"supertonic-{v}")


def melo():
    from melo.api import TTS
    m = TTS(language="KR", device="cpu")
    sid = m.hps.data.spk2id["KR"]
    sr = m.hps.data.sampling_rate

    def say(t):
        return np.asarray(m.tts_to_file(t, sid, None, speed=0.95, quiet=True), dtype=np.float32)

    build(say, sr, "melotts-KR")


if __name__ == "__main__":
    {"supertonic": supertonic, "melo": melo}[sys.argv[1]]()
