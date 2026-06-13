"""PAGE-METHOD (scalable) — lấy TRANG BẮT ĐẦU chuẩn cho mọi sách CTST từ vietjack.me sitemap.
URL vietjack.me dạng: soan-bai-{slug}-trang-{N}-chan-troi-sang-tao -> N = trang bắt đầu thật (đáng tin hơn Google).
Dùng: chạy -> /tmp/ctst_pagemap.json {slug: [trang]}. Map slug->bài của sách cần, gán tập theo số Bài (vd Văn: 1-5=T1, 6-10=T2).
Back-test Văn 9 CTST t2 (2026-06-14): 11/13 bài khớp; sai nặng nhất từng có = Kẻ sát nhân (DB 55 vs thật 47, đã sửa).
KHÔNG phủ: Đấu tranh/Bài phát biểu (sitemap thiếu slug) -> verify nguồn khác."""
#!/usr/bin/env python3
"""Page-method: vietjack.me sitemap -> {slug: trang_bắt_đầu} cho mọi sách CTST. Tái dùng."""
import re, requests, warnings, json, sys
warnings.filterwarnings("ignore")
UA={"User-Agent":"Mozilla/5.0"}
def get(u):
    try: return requests.get(u,headers=UA,timeout=15,verify=False)
    except: return None
idx=get("https://vietjack.me/sitemap.xml")
subs=re.findall(r"<loc>([^<]+)</loc>", idx.text) if idx else []
print(f"[pagemap] {len(subs)} sub-sitemaps", flush=True)
pairs={}   # slug -> set(trang)
for i,sm in enumerate(subs):
    r=get(sm)
    if r and r.status_code==200:
        for slug,tr in re.findall(r"soan-bai-([a-z0-9-]+?)-trang-(\d+)-chan-troi-sang-tao", r.text):
            pairs.setdefault(slug,set()).add(int(tr))
    if i%50==0: print(f"  ...{i}/{len(subs)} slugs={len(pairs)}", flush=True)
out={k:sorted(v) for k,v in pairs.items()}
json.dump(out,open("/tmp/ctst_pagemap.json","w"),ensure_ascii=False,indent=0)
print(f"[pagemap] TỔNG {len(out)} slug CTST có trang -> /tmp/ctst_pagemap.json", flush=True)
# in các slug khớp 13 bài + 2 bài nghi thiếu
targets=["song-day","ti-ba-hanh","mua-xuan-chin","hai-chu-nuoc-nha","cai-bong-tren-tuong","ki-uc-tuoi-tho",
"cai-roi-tre","ngoi-mo-co","ke-sat-nhan-lo-dien","cach-suy-luan","dau-tranh","phat-bieu","buc-thu-tuong-tuong","an-toan-trong-khong-gian-mang","nhung-dieu-can-biet"]
print("\n[pagemap] khớp bài quan tâm:")
for t in targets:
    hits={k:v for k,v in out.items() if t in k}
    for k,v in list(hits.items())[:3]: print(f"   {v}  {k}")
