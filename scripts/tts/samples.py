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


def speeds():
    """F1·F3 목소리를 속도별로. 마지막은 '칠 / 곱하기 / 팔' 조각을 쉬면서 이어 붙인 버전"""
    from supertonic import TTS
    tts = TTS(auto_download=True)
    sr = getattr(tts, "sample_rate", None) or 44100
    texts = ["구천팔백십 원", "사백만 오백 원", "커피는 사천 원이고, 빵은 이천 원이에요. 빵은 얼마예요?", "칠 곱하기 팔"]
    for v in ["F1", "F3"]:
        style = tts.get_voice_style(voice_name=v)
        for sp in [0.75, 0.85, 1.0]:
            def say(t):
                w, _ = tts.synthesize(t, voice_style=style, lang="ko", total_steps=10, speed=sp, silence_duration=0.1)
                return np.asarray(w, dtype=np.float32).reshape(-1)
            parts = []
            for t in texts:
                parts += [say(t), gap(sr, 1.0)]
            for p in ["칠", "곱하기", "팔"]:
                parts += [trim(say(p), sr), gap(sr, 0.4)]
            w = np.concatenate(parts)
            w = w / max(np.abs(w).max(), 1e-6) * 0.9
            sf.write(f"{OUT}/{v}-speed-{sp:.2f}.wav", w, sr)
            print("wrote", v, sp, len(w) / sr)




def natural():
    """듣고 쓰기 금액을 사람처럼 끊어 읽기 — 세 가지 방식 비교 (모두 0.7배)"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gen_pack import to_ko, natural_parts, cap_pauses
    from supertonic import TTS
    tts = TTS(auto_download=True)
    sr = getattr(tts, "sample_rate", None) or 44100
    style = tts.get_voice_style(voice_name="F1")

    def say(t):
        w, _ = tts.synthesize(t, voice_style=style, lang="ko", total_steps=10, speed=0.7, silence_duration=0.15)
        return trim(np.asarray(w, dtype=np.float32).reshape(-1), sr)

    amounts = [205880, 34500, 4000500, 3270500, 128000, 9810, 70350]
    for n in amounts:
        print(n, to_ko(n), "|", " / ".join(natural_parts(n)))
    for name, f in [
        ("1-지금(쉼없이)", lambda n: say(f"{to_ko(n)} 원")),
        ("2-쉼표로-끊기", lambda n: cap_pauses(say(", ".join(natural_parts(n)) + " 원"), sr, 0.25)),
        ("3-조각-이어붙이기", lambda n: np.concatenate(sum([[say(p + (" 원" if i == len(natural_parts(n)) - 1 else "")), gap(sr, 0.22)] for i, p in enumerate(natural_parts(n))], [])[:-1])),
    ]:
        parts = []
        for n in amounts:
            parts += [f(n), gap(sr, 1.3)]
        w = np.concatenate(parts)
        w = w / max(np.abs(w).max(), 1e-6) * 0.9
        sf.write(f"{OUT}/{name}.wav", w, sr)
        print("wrote", name, len(w) / sr)



def natsent():
    """문장 듣기 끊어 읽기 — 상품 이름 뒤에서 안 쉬기 / 살짝 쉬기 비교"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gen_pack as g
    from supertonic import TTS
    tts = TTS(auto_download=True)
    sr = getattr(tts, "sample_rate", None) or 44100
    style = tts.get_voice_style(voice_name="F1")

    def say(t):
        w, _ = tts.synthesize(t, voice_style=style, lang="ko", total_steps=10, speed=0.7, silence_duration=0.15)
        return g.cap_by_text(trim(np.asarray(w, dtype=np.float32).reshape(-1), sr), sr, t)

    _, _, sent = g.all_jobs()
    qs = [q for q in sent[1] if q["items"][0][1] >= 10000][:2] + sent[1][1:2] + sent[2][:2] + sent[4][:1]
    for name, keep in [("1-이름-뒤-안-쉼", False), ("2-이름-뒤-살짝-쉼", True)]:
        parts = []
        for q in qs:
            body, ques = g.sentence_parts(q, False, True)
            if not keep:
                body = body.replace("은,", "은").replace("는,", "는")
            print(name, body, "/", ques, g.gap_caps(body))
            parts += [say(body), gap(sr, 0.5), say(ques), gap(sr, 1.5)]
        w = np.concatenate(parts)
        w = w / max(np.abs(w).max(), 1e-6) * 0.9
        sf.write(f"{OUT}/{name}.wav", w, sr)


if __name__ == "__main__":
    {"supertonic": supertonic, "melo": melo, "speeds": speeds, "natural": natural, "natsent": natsent}[sys.argv[1]]()
