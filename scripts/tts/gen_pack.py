"""음성 팩 만들기 (GitHub Actions에서 실행)

Supertonic F1 목소리로 앱에서 쓸 소리를 모두 미리 만든다.
  m/  금액 (듣고 쓰기 · 보고 읽기 정답 듣기)      _n 0.85배 / _d 0.75배(기본) / _s 0.7배+쉼표
  s/  문장 속 금액 듣기                           _d / _s
  x/  곱셈·덧셈 문제 읽기                          _d / _s
index.json 에 레벨별 금액 묶음과 문장 문제 목록을 담는다.
"""
import json, os, random, sys, subprocess
import numpy as np, soundfile as sf

OUT = sys.argv[1] if len(sys.argv) > 1 else "voice"
WAV = OUT + "_wav"
VOICE = "F1"
SPEED = {"n": 0.85, "d": 0.75, "s": 0.70}
rnd = random.Random(20261025)

# ---------- 숫자 → 한글 (앱과 같은 규칙) ----------
DN = "영일이삼사오육칠팔구"


def u4(n):
    u = ["천", "백", "십", ""]
    t = str(n).zfill(4)
    s = ""
    for i in range(4):
        d = int(t[i])
        if d:
            s += ("" if d == 1 and u[i] else DN[d]) + u[i]
    return s


def to_ko(n):
    if not n:
        return "영"
    m = n // 10000
    return ((("" if m == 1 else u4(m)) + "만") if m else "") + u4(n % 10000)


def to_ko_parts(n):
    """쉬어 가며 읽기용: 9810 → '구천, 팔백, 십'"""
    m, r = n // 10000, n % 10000
    parts = []
    if m:
        parts.append(("" if m == 1 else u4(m)) + "만")
    u = ["천", "백", "십", ""]
    t = str(r).zfill(4)
    for i in range(4):
        d = int(t[i])
        if d:
            parts.append(("" if d == 1 and u[i] else DN[d]) + u[i])
    return ", ".join(parts)


def josa(word, a, b):
    """받침 있으면 a(은/이), 없으면 b(는/가)"""
    c = ord(word[-1]) - 0xAC00
    return a if 0 <= c <= 11171 and c % 28 else b


# ---------- 레벨별 금액 묶음 (앱의 LV 와 같은 규칙) ----------
LV = [None,
      dict(min=1, max=9, step=100, z="any"),
      dict(min=11, max=99, step=10, z="no"),
      dict(min=10, max=99, step=100, z="any"),
      dict(min=111, max=999, step=10, z="no"),
      dict(min=101, max=999, step=10, z="mid"),
      dict(min=10, max=99, step=1000, z="any"),
      dict(min=111, max=999, step=100, z="no"),
      dict(min=1001, max=9999, step=10, z="mid"),
      dict(min=100, max=999, step=1000, z="any"),
      dict(min=10001, max=99999, step=10, z="mid"),
      dict(min=1001, max=9999, step=1, z="end"),
      dict(min=10001, max=99999, step=1, z="end"),
      dict(min=10, max=99, step=100000, z="any"),
      dict(z="sparse")]
POOL = 80


def ok_k(L, k):
    s = str(k)
    if L["z"] == "no" and "0" in s:
        return False
    if L["z"] == "end" and s[-1] == "0":
        return False
    if L["z"] == "mid" and not ("0" in s[1:-1] and s[-1] != "0"):
        return False
    return True


def sparse():
    d = [rnd.randint(1, 9)] + [0] * 6
    m = 1 if rnd.random() < .5 else 2
    ch = rnd.sample(range(1, 7), m)
    if not any(p >= 2 for p in ch):
        ch[0] = rnd.randint(2, 6)
    for p in ch:
        d[p] = rnd.randint(1, 9)
    return int("".join(map(str, d)))


def money_pools():
    pools = {}
    for lv in range(1, 15):
        L = LV[lv]
        if L["z"] == "sparse":
            s = set()
            while len(s) < POOL:
                s.add(sparse())
            pools[lv] = sorted(s)
            continue
        cand = [k * L["step"] for k in range(L["min"], L["max"] + 1) if ok_k(L, k)]
        pools[lv] = sorted(rnd.sample(cand, min(POOL, len(cand))))
    return pools


# ---------- 상품 (이름, 최저가, 최고가) — 100원 단위 ----------
PRODUCTS = [
    # 과일
    ("사과", 1500, 4000), ("배", 3000, 6000), ("바나나", 2000, 5000), ("귤", 3000, 9000), ("딸기", 6000, 15000),
    ("수박", 15000, 30000), ("포도", 5000, 12000), ("복숭아", 2000, 5000), ("참외", 2000, 5000), ("키위", 3000, 7000),
    # 채소
    ("감자", 2000, 5000), ("양파", 2000, 4500), ("당근", 1000, 3000), ("오이", 800, 2000), ("대파", 2000, 4000),
    ("배추", 3000, 6000), ("무", 1500, 3500), ("상추", 1500, 3000), ("버섯", 1500, 3500), ("고구마", 3000, 7000),
    ("호박", 1500, 3500), ("시금치", 2000, 4000), ("마늘", 4000, 9000), ("콩나물", 1000, 2500),
    # 냉장
    ("우유", 2000, 3500), ("계란", 5000, 9000), ("두부", 1500, 3500), ("요구르트", 1500, 3000), ("치즈", 3000, 7000),
    ("햄", 3000, 7000), ("어묵", 3000, 6000), ("만두", 6000, 10000), ("김치", 8000, 15000),
    # 고기·생선
    ("삼겹살", 12000, 25000), ("닭고기", 7000, 12000), ("소고기", 20000, 45000), ("고등어", 4000, 8000), ("오징어", 5000, 10000),
    # 가공·간식
    ("라면", 1000, 5500), ("과자", 1500, 3500), ("빵", 2000, 5000), ("식빵", 2500, 4500), ("아이스크림", 1000, 3000),
    ("초콜릿", 1500, 4000), ("김", 3000, 7000), ("참치", 2500, 5000), ("쌀", 25000, 45000), ("국수", 2500, 5000),
    ("떡", 3000, 6000), ("케이크", 18000, 35000), ("사탕", 1500, 3500),
    # 음료
    ("커피", 3000, 6000), ("콜라", 1500, 3000), ("주스", 2000, 4000), ("생수", 800, 1500), ("녹차", 1500, 3000), ("맥주", 2500, 4500),
    # 생활용품
    ("휴지", 8000, 18000), ("치약", 3000, 7000), ("칫솔", 2000, 5000), ("비누", 1500, 4000), ("샴푸", 6000, 15000),
    ("세제", 7000, 15000), ("수건", 5000, 12000), ("양말", 3000, 8000), ("우산", 8000, 20000), ("건전지", 3000, 8000),
    ("장갑", 3000, 9000), ("슬리퍼", 5000, 12000),
    # 식당·분식
    ("김밥", 3000, 5000), ("떡볶이", 4000, 6000), ("짜장면", 6000, 8000), ("짬뽕", 7000, 9500), ("칼국수", 8000, 10000),
    ("비빔밥", 8000, 11000), ("냉면", 9000, 12000), ("돈가스", 9000, 13000), ("순대", 4000, 6000), ("붕어빵", 1000, 3000),
    ("치킨", 18000, 25000), ("피자", 15000, 28000), ("햄버거", 5000, 9000),
]


def price(p):
    _, lo, hi = p
    return rnd.randint(lo // 100, hi // 100) * 100


def sentence_pools():
    """1: 상품 하나  2: 둘, 뒤의 것  3: 둘, 아무거나  4: 셋, 하나"""
    plan = {1: 120, 2: 120, 3: 120, 4: 100}
    out = {}
    for lv, cnt in plan.items():
        lst, seen = [], set()
        while len(lst) < cnt:
            n = 1 if lv == 1 else 2 if lv <= 3 else 3
            ps = rnd.sample(PRODUCTS, n)
            items = [[p[0], price(p)] for p in ps]
            if len({it[1] for it in items}) < n:
                continue
            ask = 0 if lv == 1 else 1 if lv == 2 else rnd.randrange(n)
            key = tuple((it[0], it[1]) for it in items) + (ask,)
            if key in seen:
                continue
            seen.add(key)
            lst.append({"id": f"s{lv}_{len(lst):03d}", "items": items, "ask": ask})
        out[lv] = lst
    return out


def sentence_text(q, slow):
    items, ask = q["items"], q["ask"]
    amt = (lambda v: to_ko_parts(v)) if slow else to_ko
    c = "," if slow else ""
    nm = lambda w: w + josa(w, "은", "는")
    if len(items) == 1:
        a, v = items[0]
        return f"{nm(a)}{c} {amt(v)} 원이에요."
    if len(items) == 2:
        (a, va), (b, vb) = items
        body = f"{nm(a)}{c} {amt(va)} 원이고, {nm(b)}{c} {amt(vb)} 원이에요."
    else:
        (a, va), (b, vb), (d, vd) = items
        body = f"{nm(a)}{c} {amt(va)} 원, {nm(b)}{c} {amt(vb)} 원, {nm(d)}{c} {amt(vd)} 원이에요."
    return f"{body} {nm(items[ask][0])}{c} 얼마예요?"


# ---------- 곱셈·덧셈 문제 읽기 ----------
def math_items():
    out = []
    for a in range(2, 10):
        for b in range(2, 10):
            out.append((f"mul_{a}x{b}", f"{DN[a]} 곱하기 {DN[b]}", f"{DN[a]}, 곱하기, {DN[b]}"))
    for a in range(1, 10):
        for b in range(1, 10):
            out.append((f"add_{a}p{b}", f"{DN[a]} 더하기 {DN[b]}", f"{DN[a]}, 더하기, {DN[b]}"))
    return out


# ---------- 소리 만들기 ----------
def main():
    from supertonic import TTS
    tts = TTS(auto_download=True)
    sr = getattr(tts, "sample_rate", None) or 44100
    style = tts.get_voice_style(voice_name=VOICE)

    def synth(text, sp, path):
        w, _ = tts.synthesize(text, voice_style=style, lang="ko", total_steps=10, speed=sp, silence_duration=0.15)
        w = np.asarray(w, dtype=np.float32).reshape(-1)
        a = np.abs(w)
        idx = np.where(a > 0.01 * max(a.max(), 1e-6))[0]
        if len(idx):
            w = w[max(0, idx[0] - int(sr * .03)): min(len(w), idx[-1] + int(sr * .12))]
        w = w / max(np.abs(w).max(), 1e-6) * 0.92
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sf.write(path, w, sr)

    jobs = []
    money = money_pools()
    amounts = sorted({v for lv in money for v in money[lv]})
    for v in amounts:
        jobs.append((f"m/{v}_n", f"{to_ko(v)} 원", SPEED["n"]))
        jobs.append((f"m/{v}_d", f"{to_ko(v)} 원", SPEED["d"]))
        jobs.append((f"m/{v}_s", f"{to_ko_parts(v)} 원", SPEED["s"]))
    sent = sentence_pools()
    for lv in sent:
        for q in sent[lv]:
            jobs.append((f"s/{q['id']}_d", sentence_text(q, False), SPEED["d"]))
            jobs.append((f"s/{q['id']}_s", sentence_text(q, True), SPEED["s"]))
    maths = math_items()
    for key, t, ts in maths:
        jobs.append((f"x/{key}_d", t, SPEED["d"]))
        jobs.append((f"x/{key}_s", ts, SPEED["s"]))

    print(f"{len(amounts)} amounts, {sum(len(v) for v in sent.values())} sentences, {len(maths)} math, {len(jobs)} clips", flush=True)
    for i, (name, text, sp) in enumerate(jobs):
        synth(text, sp, f"{WAV}/{name}.wav")
        if i % 200 == 0:
            print(i, name, text, flush=True)

    # ogg(opus)로 압축
    subprocess.run(f"cd {WAV} && find . -name '*.wav' | sed 's/\\.wav$//' | xargs -P 8 -I{{}} sh -c "
                   f"'mkdir -p ../{OUT}/$(dirname {{}}) && ffmpeg -loglevel error -y -i {{}}.wav -ac 1 -ar 24000 -c:a libopus -b:a 24k ../{OUT}/{{}}.ogg'",
                   shell=True, check=True)

    index = {"v": 1, "voice": VOICE,
             "money": {str(k): v for k, v in money.items()},
             "sent": {str(k): v for k, v in sent.items()},
             "math": [k for k, _, _ in maths]}
    with open(f"{OUT}/index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    print("done")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--dry":
        m = money_pools(); s = sentence_pools()
        print({k: len(v) for k, v in m.items()})
        for lv in s:
            for q in s[lv][:3]:
                print(lv, sentence_text(q, False), "|", sentence_text(q, True))
        print(len(math_items()))
    else:
        main()
