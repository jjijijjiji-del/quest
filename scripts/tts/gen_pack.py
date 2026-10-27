"""음성 팩 만들기 (GitHub Actions에서 실행)

Supertonic F1 목소리로 앱에서 쓸 소리를 모두 미리 만든다.
  m/  금액 (듣고 쓰기 · 보고 읽기 정답 듣기)      _d 0.75배(기본) / _s 0.7배 / _c 0.7배+쉼표
  s/  문장 속 금액 듣기                           _d / _s
  x/  곱셈·덧셈 문제 읽기                          _d / _s
index.json 에 레벨별 금액 묶음과 문장 문제 목록을 담는다.
"""
import json, os, random, sys, subprocess, traceback

OUT = sys.argv[1] if len(sys.argv) > 1 else "voice"
WAV = OUT + "_wav"
VOICE = "F1"
SPEED = {"d": 0.75, "s": 0.70, "c": 0.70, "n": 0.70}  # c = 0.7배 + 쉼표로 쉬어 가기, n = 0.7배 + 만·천 자리에서 살짝 끊기
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


def natural_parts(n):
    """손님에게 금액을 알려 주듯 끊어 읽기 (짧으면 이어서, 길면 끝의 십·일 단위를 떼어서)
    9810 → 구천팔백, 십   205880 → 이십만, 오천팔백, 팔십   15000 → 만오천   34500 → 삼만, 사천오백"""
    m, r = n // 10000, n % 10000
    rest = []
    rw = u4(r)
    if len(rw) >= 5 and r % 100:
        head, tail = u4(r - r % 100), u4(r % 100)
        rest = [head, tail] if head else [tail]
    elif rw:
        rest = [rw]
    if not m:
        return rest or ["영"]
    mw = ("" if m == 1 else u4(m)) + "만"
    if not rest:
        return [mw]
    if len(mw) == 1:
        # '만'으로 시작하면 '마안, 이천' 처럼 만을 살짝 끌고 아주 짧게 쉼
        return [mw] + rest
    if len(mw) + len(rw) < 5:
        return [mw + rest[0]] + rest[1:]
    return [mw] + rest


def cap_pauses(w, sr, cap=0.25, th=0.02, first=None):
    """말 사이 조용한 구간을 cap초로 줄임 (앞뒤는 그대로)"""
    import numpy as np
    f = int(sr * .02)
    n = len(w) // f
    if n < 3:
        return w
    lv = np.abs(w[:n * f]).reshape(n, f).max(axis=1)
    loud = lv > th * max(lv.max(), 1e-6)
    idx = np.where(loud)[0]
    if not len(idx):
        return w
    keep = int(cap / .02)
    out, i, gaps = [w[:idx[0] * f]], idx[0], 0
    while i <= idx[-1]:
        j = i
        while j <= idx[-1] and loud[j] == loud[i]:
            j += 1
        seg = w[i * f:j * f]
        k = int(first / .02) if first and gaps == 0 else keep
        if not loud[i] and (j - i) > k:
            h = k // 2
            seg = np.concatenate([seg[:h * f], seg[-(k - h) * f:]])
        if not loud[i] and (j - i) >= 4:
            gaps += 1
        out.append(seg)
        i = j
    out.append(w[(idx[-1] + 1) * f:])
    return np.concatenate(out)


def gap_caps(text):
    """글 속 쉼표·마침표마다 쉬는 시간 상한 — 금액을 다시 물어본 사람에게 또박또박 친절하게 알려 주는 정도.
    '만,' 0.12초 / 금액 안 0.25초 (듣고 쓰기와 문장 듣기 같음) / '짬뽕은,' 0.2초 / 상품 사이 0.35초"""
    t = text.rstrip(" .?!")
    caps = []
    for i, ch in enumerate(t):
        if ch not in ",.":
            continue
        before = t[:i].split(" ")[-1]
        after = t[i + 1:].lstrip().split(" ")[0].rstrip(",.")
        num = lambda w: bool(w) and all(c in "일이삼사오육칠팔구십백천만" for c in w)
        if before == "만" and num(after):
            caps.append(0.12)
        elif num(before) and num(after):
            caps.append(0.25)
        elif before[-1:] in "은는" and num(after):
            caps.append(0.2)
        else:
            caps.append(0.35)
    return caps


def cap_by_text(w, sr, text, th=0.02, report=None):
    """쉬는 곳마다 글의 어느 쉼표인지 찾아(말한 시간 비율 ↔ 글자 위치) 그 쉼표의 상한으로 줄임.
    쉼표에 해당하지 않는 쉼(글자 사이 숨)은 0.1초로. 쉼 수가 글과 달라도 자리별로 맞음"""
    import numpy as np
    caps = gap_caps(text)
    t = text.rstrip(" .?!")
    # 쉼표 앞 글자 수 (공백·문장부호 빼고)
    syl = lambda u: sum(1 for ch in u if "가" <= ch <= "힣")
    pos = [syl(t[:i]) for i, ch in enumerate(t) if ch in ",."]
    total = max(1, syl(t))
    f = int(sr * .02)
    n = len(w) // f
    if n < 3:
        return w
    lv = np.abs(w[:n * f]).reshape(n, f).max(axis=1)
    loud = lv > th * max(lv.max(), 1e-6)
    idx = np.where(loud)[0]
    if not len(idx):
        return w
    runs_ = []
    i = idx[0]
    while i <= idx[-1]:
        j = i
        while j <= idx[-1] and loud[j] == loud[i]:
            j += 1
        runs_.append((i, j, bool(loud[i])))
        i = j
    speech = sum(b - a for a, b, l in runs_ if l)
    out, said, used = [w[:idx[0] * f]], 0, set()
    for a, b, l in runs_:
        seg = w[a * f:b * f]
        if l:
            said += b - a
        elif b - a >= 4:
            at = said / max(1, speech) * total
            best = min(range(len(pos)), key=lambda k: abs(pos[k] - at), default=None)
            if best is not None and abs(pos[best] - at) <= 1.6 and best not in used:
                cap = caps[best]
                used.add(best)
            else:
                cap = 0.1
            if report is not None:
                report.append((round(at, 1), best, cap, round((b - a) * .02, 2)))
            keep = int(cap / .02)
            if b - a > keep:
                h = keep // 2
                seg = np.concatenate([seg[:h * f], seg[-(keep - h) * f:]])
        out.append(seg)
    out.append(w[(idx[-1] + 1) * f:])
    return np.concatenate(out)


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


def sentence_text(q, slow, nat=False):
    items, ask = q["items"], q["ask"]
    amt = (lambda v: to_ko_parts(v)) if slow else (lambda v: ", ".join(natural_parts(v))) if nat else to_ko
    c = "," if slow or nat else ""
    nm = lambda w: w + josa(w, "은", "는")
    if len(items) == 1:
        a, v = items[0]
        body = f"{nm(a)}{c} {amt(v)} 원이에요."
    elif len(items) == 2:
        (a, va), (b, vb) = items
        body = f"{nm(a)}{c} {amt(va)} 원이고, {nm(b)}{c} {amt(vb)} 원이에요."
    else:
        (a, va), (b, vb), (d, vd) = items
        body = f"{nm(a)}{c} {amt(va)} 원, {nm(b)}{c} {amt(vb)} 원, {nm(d)}{c} {amt(vd)} 원이에요."
    return f"{body} {nm(items[ask][0])}{',' if slow else ''} 얼마예요?"


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


# ---------- 받아 적은 글에서 숫자 찾기 (검사용) ----------
NUMC = set("0123456789일이삼사오육륙칠팔구십백천만")
KD = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9}
UN = {"십": 10, "백": 100, "천": 1000}


def parse_run(r):
    total = sec = 0
    num = None
    i = 0
    while i < len(r):
        ch = r[i]
        if ch.isdigit():
            j = i
            while j < len(r) and r[j].isdigit():
                j += 1
            num = int(r[i:j]); i = j; continue
        if ch in KD:
            num = KD[ch]
        elif ch in UN:
            sec += (num if num is not None else 1) * UN[ch]; num = None
        elif ch == "만":
            sec += num or 0
            total += (sec or 1) * 10000; sec = 0; num = None
        i += 1
    return total + sec + (num or 0)


def runs(t):
    out, cur = [], ""
    for ch in t:
        if ch in NUMC:
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def clean(t):
    return t.replace(" ", "").replace(",", "").replace(".", "").replace("?", "")


def check_money(text, v):
    rs = runs(clean(text))
    return bool(rs) and parse_run(max(rs, key=len)) == v


from difflib import SequenceMatcher
import re as _re


def name_ok(name, word):
    """받아 적기에서 흔한 표기 차이를 봐줌 (돈가스→돈까스, 칫솔→치솔, 오이→5위)"""
    if not word:
        return False
    if len(name) == 1:
        return True
    return name in word or SequenceMatcher(None, name, word).ratio() >= 0.5


def check_sentence(text, q):
    t = clean(text)
    if "원" not in t:
        return False
    segs = t.split("원")
    prices = []
    for seg in segs[:-1]:
        rs = runs(seg)
        if not rs:
            return False
        prices.append(parse_run(rs[-1]))
    want = [it[1] for it in q["items"]]
    if prices[:len(want)] != want:
        return False
    if True:
        # 질문에 상품 이름이 빠지지 않았는지 (이번에 고치려는 오류)
        if "얼마" not in segs[-1]:
            return False
        pre = segs[-1].split("얼마")[0]
        pre = _re.sub(r"^(이에요|에요|예요|이고|이요)", "", pre)
        word = _re.sub(r"[은는]$", "", pre)
        if not name_ok(q["items"][q["ask"]][0], word):
            return False
    return True


def check_math(text, a, b, op):
    t = clean(text)
    if "기" not in t and "×" not in t and "+" not in t and "x" not in t.lower():
        return False
    vals = [parse_run(r) for r in runs(_re.sub(r"(곱|고|급|더|도|드|두)[가-힣]{0,2}기", "|", t))]
    return vals[:2] == [a, b]


# ---------- 할 일 목록 ----------
def all_jobs():
    """(파일 이름, [(글, 쉬는 시간)...], 속도, 검사 종류, 검사 값)"""
    jobs = []
    money = money_pools()
    for v in sorted({v for lv in money for v in money[lv]}):
        jobs.append((f"m/{v}_d", [f"{to_ko(v)} 원"], "d", "money", v))
        jobs.append((f"m/{v}_s", [f"{to_ko(v)} 원"], "s", "money", v))
        jobs.append((f"m/{v}_c", [f"{to_ko_parts(v)} 원"], "c", "money", v))
        jobs.append((f"m/{v}_n", [NAT_TEXT(v)], "n", "money", v))
    sent = sentence_pools()
    for lv in sent:
        for q in sent[lv]:
            for sv, slow in (("d", False), ("s", False), ("c", True), ("n", False)):
                body, ques = sentence_parts(q, slow, sv == "n")
                jobs.append((f"s/{q['id']}_{sv}", [body] + ([ques] if ques else []), sv, "sent", q))
    for key, t, ts in math_items():
        a, b = int(key[4]), int(key[6])
        op = "곱하기" if key.startswith("mul") else "더하기"
        jobs.append((f"x/{key}_d", [t], "d", "math", (a, b, op)))
        jobs.append((f"x/{key}_s", [t], "s", "math", (a, b, op)))
        jobs.append((f"x/{key}_c", [ts], "c", "math", (a, b, op)))
    return jobs, money, sent


def sentence_parts(q, slow, nat=False):
    """문장과 질문을 따로: 질문을 따로 만들어야 상품 이름이 빠지는 오류가 줄어듦"""
    full = sentence_text(q, slow, nat)
    i = full.rfind(". ")
    return full[:i + 1], full[i + 2:]


# 끊어 읽기 소리 만드는 방법: 쉼표를 넣고 쉬는 시간을 줄임
NAT_TEXT = lambda v: ", ".join(natural_parts(v)) + " 원"
NAT_GAP = 0.25

# 이번에 다시 만들 것: 끊어 읽는 금액 전부, 상품 하나 문장(질문 추가), 바뀐 단어
UPDATE_WORDS = {"g11_3"}


def update_jobs():
    """이번에 새로 만들 것: 문장 듣기 끊어 읽기(n) 중 금액 안에서 끊는 문장 ('만' 뒤가 길게 쉬던 것 고치기)"""
    jobs, _, _ = all_jobs()
    return [j for j in jobs if j[3] == "sent" and j[2] == "n" and "만," in j[1][0]]


# ---------- 소리 만들기 ----------
TRIES = [(0, 10), (.02, 12), (.04, 8), (0, 14), (.03, 6), (.01, 12), (.05, 10)]


# 받아 적을 때 숫자를 한글로 적도록 유도 (아라비아 숫자로 바꾸면서 생기는 오류를 줄임)
PROMPT = "숫자는 한글로 적습니다. 구천팔백십 원. 삼백육만 원. 만사백 원. 칠 곱하기 팔. 육 더하기 육."


# ---------- 순서 기억: 그림 카드 단어 (www/cards/cards.json) ----------
def word_jobs():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "www", "cards", "cards.json")
    cards = json.load(open(path, encoding="utf-8"))
    return [(f"w/{c['id']}", [c["w"]], "s", "word", c["w"]) for c in cards]


def check_word(text, w):
    t = clean(text)
    t = _re.sub(r"[^가-힣a-zA-Z0-9]", "", t)
    if not t:
        return False
    alias = {"티비": ["tv", "티브이"], "휴대폰": ["핸드폰", "휴대전화"], "킥보드": ["킥보드"], "보트": ["boat"]}
    return name_ok(w, t) or w in t or any(x in t.lower() for x in alias.get(w, []))


def main(shard, nshard, only=None, recheck_dir=None, words=False, update=False):
    import numpy as np, soundfile as sf
    from supertonic import TTS
    from faster_whisper import WhisperModel
    tts = TTS(auto_download=True)
    sr = getattr(tts, "sample_rate", None) or 44100
    style = tts.get_voice_style(voice_name=VOICE)
    asr = WhisperModel("large-v3" if only is not None else "small", device="cpu", compute_type="int8")

    def synth(text, sp, steps=10):
        w, _ = tts.synthesize(text, voice_style=style, lang="ko", total_steps=steps, speed=max(0.7, sp), silence_duration=0.15)
        w = np.asarray(w, dtype=np.float32).reshape(-1)
        a = np.abs(w)
        idx = np.where(a > 0.01 * max(a.max(), 1e-6))[0]
        if len(idx):
            w = w[max(0, idx[0] - int(sr * .03)): min(len(w), idx[-1] + int(sr * .12))]
        if sv_now[0] == "n":
            return cap_by_text(w, sr, text)
        return w

    sv_now = [""]

    def hear(w):
        x = w
        if sr != 16000:
            n = int(len(w) * 16000 / sr)
            x = np.interp(np.linspace(0, len(w) - 1, n), np.arange(len(w)), w).astype(np.float32)
        segs, _ = asr.transcribe(x, language="ko", beam_size=3, vad_filter=False, condition_on_previous_text=False, initial_prompt=PROMPT)
        return " ".join(s.text for s in segs).strip()

    jobs = update_jobs() if update else word_jobs() if words else all_jobs()[0]
    mine = [j for j in jobs if j[0] in only] if only is not None else jobs[shard::nshard]
    tries = TRIES if only is not None else TRIES[:5]
    report = []
    errors = 0
    def check(kind, heard, val):
        if kind == "money":
            return check_money(heard, val)
        if kind == "sent":
            return check_sentence(heard, val)
        if kind == "word":
            return check_word(heard, val)
        return check_math(heard, *val)

    rechecked = 0
    for i, (name, texts, sv, kind, val) in enumerate(mine):
        ok, heard, w = False, "", None
        if recheck_dir:
            src = f"{recheck_dir}/{name}.ogg"
            if os.path.exists(src):
                tmp = "/tmp/rc.wav"
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-ac", "1", "-ar", "16000", tmp], check=True)
                x, _ = sf.read(tmp, dtype="float32")
                segs, _ = asr.transcribe(x, language="ko", beam_size=3, condition_on_previous_text=False, initial_prompt=PROMPT)
                heard = " ".join(sg.text for sg in segs).strip()
                if check(kind, heard, val):
                    rechecked += 1
                    report.append({"name": name, "ok": True, "tries": 0, "heard": heard, "text": " / ".join(texts)})
                    print(i, len(mine), name, "RECHECK OK |", " / ".join(texts), "→", heard, flush=True)
                    continue
        for attempt in range(len(tries)):
          try:
              dsp, steps = tries[attempt]
              sp = SPEED[sv] + dsp
              sv_now[0] = sv
              parts = []
              for j, t in enumerate(texts):
                  if j:
                      parts.append(np.zeros(int(sr * (.7 if sv == "c" else .9 if sv == "n" else .5)), dtype=np.float32))  # 문장과 질문 사이
                  parts.append(synth(t, sp, steps))
              w = np.concatenate(parts)
              w = w / max(np.abs(w).max(), 1e-6) * 0.92
              heard = hear(w)
              ok = check(kind, heard, val)
              if ok:
                  break
          except Exception as e:
            errors += 1
            heard = f"ERROR {e!r}"
            if errors <= 10:
                print(f"::warning::{name} 시도 {attempt + 1}: {e!r}"[:900], flush=True)
                traceback.print_exc()
        if w is None or not len(w):
            print(f"::warning::{name} 소리를 만들지 못함", flush=True)
            report.append({"name": name, "ok": False, "tries": 5, "heard": heard, "text": " / ".join(texts)})
            continue
        os.makedirs(os.path.dirname(f"{WAV}/{name}.wav"), exist_ok=True)
        sf.write(f"{WAV}/{name}.wav", w, sr)
        report.append({"name": name, "ok": ok, "tries": attempt + 1, "heard": heard, "text": " / ".join(texts)})
        if i % 50 == 0 or not ok:
            print(i, len(mine), name, "OK" if ok else "FAIL", attempt + 1, "|", " / ".join(texts), "→", heard, flush=True)

    os.makedirs(WAV, exist_ok=True)
    subprocess.run(f"cd {WAV} && find . -name '*.wav' | sed 's/\\.wav$//' | xargs -P 4 -I{{}} sh -c "
                   f"'mkdir -p ../{OUT}/$(dirname {{}}) && ffmpeg -loglevel error -y -i {{}}.wav -ac 1 -ar 24000 -c:a libopus -b:a 24k ../{OUT}/{{}}.ogg'",
                   shell=True, check=True)
    os.makedirs("report", exist_ok=True)
    with open(f"report/shard{shard}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=0)
    bad = [r for r in report if not r["ok"]]
    if recheck_dir:
        print(f"::notice::고치기 {shard}: {len(report)}개 중 다시 들어 보니 맞은 것 {rechecked}개, 다시 만들어 맞은 것 {sum(r['ok'] and r['tries'] > 0 for r in report)}개, 여전히 실패 {len(bad)}개", flush=True)
    print(f"::notice::shard {shard}: {len(report)}개, 다시 만든 것 {sum(r['tries'] > 1 for r in report)}개, 검사 실패 {len(bad)}개, 오류 {errors}번", flush=True)
    print(f"shard {shard}: {len(report)} clips, retried {sum(r['tries'] > 1 for r in report)}, still failing {len(bad)}")


def write_index():
    _, money, sent = all_jobs()
    os.makedirs(OUT, exist_ok=True)
    index = {"v": 2, "voice": VOICE,
             "money": {str(k): v for k, v in money.items()},
             "sent": {str(k): v for k, v in sent.items()},
             "math": [k for k, _, _ in math_items()], "nat": True}
    with open(f"{OUT}/index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    # gen_pack.py voice shard 0 6   /   gen_pack.py voice index   /   gen_pack.py voice dry
    cmd = sys.argv[2] if len(sys.argv) > 2 else "dry"
    if cmd == "shard":
        main(int(sys.argv[3]), int(sys.argv[4]))
    elif cmd == "repair":
        # 검사에서 실패했던 소리만 다시 만들기: gen_pack.py voice repair failures.json
        # gen_pack.py out repair failures.json 0 4 old_voice_dir
        names = sorted(r["name"] for r in json.load(open(sys.argv[3], encoding="utf-8")))
        k, n = int(sys.argv[4]), int(sys.argv[5])
        main(k, n, only=set(names[k::n]), recheck_dir=sys.argv[6])
    elif cmd == "words":
        # 단어 소리만 만들기: gen_pack.py out words
        main(0, 1, words=True)
    elif cmd == "update":
        # gen_pack.py out update 0 6
        main(int(sys.argv[3]), int(sys.argv[4]), update=True)
    elif cmd == "index":
        write_index()
    else:
        jobs, m, s = all_jobs()
        print(len(jobs), {k: len(v) for k, v in m.items()})
        for j in jobs[:2] + [x for x in jobs if x[3] == "sent"][:3] + [x for x in jobs if x[3] == "math"][:2]:
            print(j[0], j[1], j[2])
        print(check_sentence("만두는 9000원이고, 두부는 3000원이에요. 두부는 얼마예요?", {"items": [["만두", 9000], ["두부", 3000]], "ask": 1}),
              check_sentence("만두는 9000원이고, 두부는 3000원이에요. 얼마예요?", {"items": [["만두", 9000], ["두부", 3000]], "ask": 1}),
              check_money("구천 팔백십 원", 9810), check_money("9,810원", 9810), check_money("백만 십 원", 1000010),
              check_math("7 곱하기 8", 7, 8, "곱하기"), check_math("칠, 곱하기, 팔", 7, 8, "곱하기"))
