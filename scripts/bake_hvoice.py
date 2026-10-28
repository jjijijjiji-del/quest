"""보호자 녹음 묶음(앱의 '내보내기' zip)을 앱 안 www/hvoice/ 로 넣기 (APK 빌드 때 실행)
   python3 scripts/bake_hvoice.py human-voice.zip www/hvoice"""
import json, os, subprocess, sys, zipfile

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
z = zipfile.ZipFile(src)
units = json.loads(z.read("index.json"))["units"]
idx = {}
for i, (text, name) in enumerate(sorted(units.items())):
    wav = f"/tmp/hv_{i}.wav"
    open(wav, "wb").write(z.read(name))
    ogg = f"h{i:03d}.ogg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-ac", "1", "-ar", "24000", "-c:a", "libopus", "-b:a", "40k",
                    os.path.join(out, ogg)], check=True)
    idx[text] = ogg
json.dump({"v": 1, "units": idx}, open(os.path.join(out, "index.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"보호자 녹음 조각 {len(idx)}개를 넣었어요")
