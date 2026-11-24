"""그림 카드 만들기 (GitHub Actions에서 실행 — 작업 공간에서는 인터넷이 막혀 있어서)
   python3 scripts/img/gen.py scripts/img/list.txt img_out
   list.txt: 한 줄에 '이름|그릴 것(영어)'. 무료 이미지 생성(pollinations) → 실패하면 기록만."""
import sys, os, time, json, urllib.parse, urllib.request
src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
STYLE = ("studio product photograph of {}, single object only, centered, isolated on pure white background, "
         "soft natural shadow, realistic, high detail, no text, no people, no hands")
log = []
for ln in open(src, encoding="utf-8"):
    ln = ln.strip()
    if not ln or ln.startswith("#"): continue
    name, what = [s.strip() for s in ln.split("|", 1)]
    style = what if what.startswith("!") else STYLE.format(what)
    style = style.lstrip("!")
    ok = False
    for t in range(4):
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(style) +
               f"?width=768&height=768&nologo=true&seed={7+t}&model=flux")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 card-maker"})
            data = urllib.request.urlopen(req, timeout=180).read()
            if len(data) > 5000 and data[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xdb", b"RIFF"):
                ext = "png" if data[:4] == b"\x89PNG" else "webp" if data[:4] == b"RIFF" else "jpg"
                open(os.path.join(out, f"{name}.{ext}"), "wb").write(data); ok = True; break
            print("이상한 응답", name, len(data), data[:80])
        except Exception as e:
            print("실패", name, t, e)
        time.sleep(20)
    log.append({"name": name, "ok": ok})
    print(("OK " if ok else "FAIL ") + name, flush=True)
    time.sleep(16)
json.dump(log, open(os.path.join(out, "log.json"), "w"), ensure_ascii=False, indent=1)
print(f"::notice::{sum(l['ok'] for l in log)}/{len(log)}장 만듦")
