"""그림 카드를 공개 모델(SDXL-Turbo)로 직접 만들기 — GitHub Actions CPU에서 실행, 계정·비용 없음
   python3 scripts/img/gen_local.py scripts/img/list.txt img_out [장수]"""
import sys, os, time, json, torch
from diffusers import AutoPipelineForText2Image
src, out = sys.argv[1], sys.argv[2]; n = int(sys.argv[3]) if len(sys.argv) > 3 else 2
os.makedirs(out, exist_ok=True)
STYLE = ("professional studio product photo of {}, single object, centered, isolated on plain pure white background, "
         "soft shadow, photorealistic, sharp focus")
torch.set_num_threads(os.cpu_count())
t0 = time.time()
pipe = AutoPipelineForText2Image.from_pretrained("stabilityai/sdxl-turbo", torch_dtype=torch.bfloat16, variant="fp16")
print("모델 준비", round(time.time() - t0), "초", flush=True)
log = []
for ln in open(src, encoding="utf-8"):
    ln = ln.strip()
    if not ln or ln.startswith("#"): continue
    name, what = [s.strip() for s in ln.split("|", 1)]
    prompt = what[1:] if what.startswith("!") else STYLE.format(what)
    for k in range(n):
        t = time.time()
        g = torch.Generator().manual_seed(100 + k)
        im = pipe(prompt=prompt, num_inference_steps=4, guidance_scale=0.0, width=512, height=512, generator=g).images[0]
        im.save(os.path.join(out, f"{name}_{k+1}.png"))
        print(f"OK {name}_{k+1} {round(time.time()-t)}초", flush=True)
    log.append(name)
json.dump(log, open(os.path.join(out, "log.json"), "w"), ensure_ascii=False)
