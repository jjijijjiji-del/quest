"""문장 듣고 시간·숫자 고르기: items.txt → tq.json (보여 줄 문장, 읽을 문장, 질문, 정답, 틀린 보기 셋)
틀린 보기는 정답과 한 군데만 다르게 (숫자만 / 뒤에·전에만 / 오전·오후만 / 옆·앞만 / 장소만)"""
import json, re, random, sys
R = random.Random(20261128)
NAT = {1:"한",2:"두",3:"세",4:"네",5:"다섯",6:"여섯",7:"일곱",8:"여덟",9:"아홉",10:"열",11:"열한",12:"열두",20:"스무"}
SN = "영일이삼사오육칠팔구"
def sino(n):
    if n < 10: return SN[n]
    t, o = divmod(n, 10)
    return ("" if t == 1 else SN[t]) + "십" + (SN[o] if o else "")
def nat(n):
    if n in NAT: return NAT[n]
    t, o = divmod(n, 10)
    return {1:"열",2:"스물",3:"서른",4:"마흔"}[t] + (NAT[o] if o else "")
MON = lambda m: {6:"유",10:"시"}.get(m, sino(m))

# ---- 읽기(TTS용) ----
def say_t(v):
    m = re.fullmatch(r"(오전 |오후 |아침 |저녁 |밤 )?(\d+)시( 반)?", v)
    return (m[1] or "") + nat(int(m[2])) + " 시" + (m[3] or "")
def say_r(v):
    m = re.fullmatch(r"(\d+)(분|시간|일) (뒤에|전에)", v)
    if not m: return v
    n, u, d = int(m[1]), m[2], m[3]
    return (nat(n) + " 시간" if u == "시간" else sino(n) + " " + u) + " " + d
def say_num(v, kind):
    m = re.fullmatch(r"(\d+)(.*)", v); n, rest = int(m[1]), m[2]
    if kind == "f": return sino(n) + " 층"
    if kind == "x": return sino(n) + " " + rest.strip()
    if kind == "m":
        mm = re.fullmatch(r"(\d+)월 (\d+)일", v); return MON(int(mm[1])) + "월 " + sino(int(mm[2])) + "일"
    if kind == "c": return nat(n) + " " + rest
    if kind == "k": return nat(n) + " " + rest
SAY = {"t": say_t, "r": say_r, "d": lambda v: v, "p": lambda v: v}
def say(kind, v): return SAY[kind](v) if kind in SAY else say_num(v, kind)

# ---- 틀린 보기 ----
WD = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]
PLACE_B = ["병원","은행","약국","마트","우체국","학교","편의점","시장","카페"]
BUILD = PLACE_B + ["정문","건물","엘리베이터"]
# 집 안 물건은 관계마다 말이 되는 것만 (책상 안·현관 위 같은 말은 안 나오게)
PLACE_F = {"안":["가방","서랍","냉장고","지갑","상자"],"위":["책상","식탁","소파","침대","냉장고"],"밑":["침대","소파","책상","식탁"],
           "아래":["침대","소파","책상","세면대"],"앞":["현관","문","소파","냉장고","책상"],"옆":["현관","문","소파","냉장고","책상","침대"],"뒤":["문","소파","냉장고"]}
REL = {"안":["위","옆"],"위":["밑","옆"],"밑":["위","옆"],"아래":["위","옆"],"옆":["앞","뒤"],"앞":["옆","뒤"],"뒤":["앞","옆"],"건너편":["옆","앞"]}
def opts_t(v):
    m = re.fullmatch(r"(오전 |오후 |아침 |저녁 |밤 )?(\d+)시( 반)?", v); p, h, half = m[1] or "", int(m[2]), m[3] or ""
    sw = {"오전 ":"오후 ","오후 ":"오전 ","아침 ":"저녁 ","저녁 ":"아침 ","밤 ":"아침 "}
    hh = [x for x in (h - 1, h + 1) if 1 <= x <= 12]
    c = [f"{p}{hh[0]}시{half}"]
    if p: c.append(f"{sw[p]}{h}시{half}")
    c.append(f"{p}{h}시{'' if half else ' 반'}")
    if len(c) < 3 or not p: c.append(f"{p}{hh[-1] if len(hh)>1 else h-2}시{half}")
    if h == 12: c[0] = f"{p}2시{half}"          # 열두 시 ↔ 두 시 (소리가 비슷)
    return c[:3]
def opts_d(v, sent=""):
    if v in ("어제","오늘","내일","모레"):
        o = [x for x in ("어제","오늘","내일","모레") if x != v]; return o
    m = re.fullmatch(r"(다음 주 |이번 주 )?(.요일)( 저녁| 아침)?", v); w, day, tm = m[1] or "", m[2], m[3] or ""
    i = WD.index(day); nb = WD[(i + 1) % 7]; nb2 = WD[(i - 1) % 7]
    if w == "다음 주 ": return [f"이번 주 {day}{tm}", f"다음 주 {nb}{tm}", f"다음 달 {day}{tm}"]
    if w == "이번 주 ": return [f"다음 주 {day}{tm}", f"이번 주 {nb}{tm}", f"이번 주 {nb2}{tm}"]
    if tm: return [f"{day}{' 아침' if tm==' 저녁' else ' 저녁'}", f"{nb}{tm}", f"{nb2}{tm}"]
    if "다음 주" in sent: return [nb, nb2, WD[(i + 2) % 7]]   # '다음 주 수요일'이 실제로 맞는 말이 되지 않게
    return [nb, nb2, f"다음 주 {day}"]
SPECIAL_R = {"일주일 뒤에":["일주일 전에","이틀 뒤에","한 달 뒤에"],"이틀 전에":["이틀 뒤에","사흘 전에","일주일 전에"],"한 달 뒤에":["한 달 전에","두 달 뒤에","일주일 뒤에"]}
def opts_r(v):
    if v in SPECIAL_R: return SPECIAL_R[v]
    m = re.fullmatch(r"(\d+)(분|시간|일) (뒤에|전에)", v); n, u, d = int(m[1]), m[2], m[3]
    n2 = {5:15,10:20,30:3,1:2,3:13,20:2,40:4,2:3,4:14,15:50}.get(n, n + 10)
    other = "전에" if d == "뒤에" else "뒤에"
    u2 = {"분": f"{n}시에" if n <= 12 else f"{n//10}시간 {d}", "시간": f"{n}시에", "일": f"{n}주 {d}"}[u]
    return [f"{n2}{u} {d}", f"{n}{u} {other}", u2]
def opts_p(v, sent):
    lm, rel = v.rsplit(" ", 1); pool = PLACE_B if lm in BUILD else PLACE_F[rel]
    other = R.choice([x for x in pool if x != lm and x not in sent])
    a, b = REL[rel]
    return [f"{lm} {a}", f"{lm} {b}", f"{other} {rel}"]
def opts_num(v, kind):
    if kind == "m":
        mm = re.fullmatch(r"(\d+)월 (\d+)일", v); mo, d = int(mm[1]), int(mm[2])
        d2 = d + 10 if d < 20 else d - 10; mo2 = mo + 1 if mo < 12 else mo - 1
        return [f"{mo}월 {d2}일", f"{mo2}월 {d}일", f"{mo}월 {d+1 if d<28 else d-1}일"]
    m = re.fullmatch(r"(\d+)(.*)", v); n, rest = int(m[1]), m[2]
    alt = {"f": [n + 1, n - 1 if n > 1 else n + 2, n + 10], "x": [n + 1, n - 1 if n > 1 else n + 2, n + 10],
           "c": [n + 1, n - 1 if n > 1 else n + 2, n + 10 if n >= 3 else n + 2], "k": [n + 1, n - 1 if n > 1 else 3, n + 2]}[kind]
    return [f"{x}{rest}" for x in alt]
def options(kind, v, sent):
    if kind == "t": return opts_t(v)
    if kind == "d": return opts_d(v, sent)
    if kind == "r": return opts_r(v)
    if kind == "p": return opts_p(v, sent)
    return opts_num(v, kind)

out = []
for ln in open(sys.argv[1], encoding="utf-8"):
    if ln.startswith("#") or not ln.strip(): continue
    lv, s, q = ln.rstrip("\n").split("|")
    m = re.search(r"\[(\w):([^\]]+)\]", s); kind, ans = m[1], m[2]
    text = re.sub(r"[\[{]\w:([^\]}]+)[\]}]", r"\1", s)
    spoken = re.sub(r"[\[{](\w):([^\]}]+)[\]}]", lambda x: say(x[1], x[2]), s)
    o = options(kind, ans, text)
    assert len(set(o)) == 3 and ans not in o, (s, o)
    out.append({"id": len(out), "lv": int(lv), "kind": kind, "text": text, "say": spoken, "q": q, "ans": ans, "wrong": o, "ans_say": say(kind, ans)})
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "문제")
