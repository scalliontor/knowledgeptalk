"""
crawl_ngu_van_full.py
=====================
Crawl TOÀN BỘ Ngữ Văn lớp 9 từ loigiaihay.com — 4 nguồn:

  1. SOẠN BÀI  (3 series: CTST, KNTT, CD)
     → loigiaihay.com/soan-van-9-*-c*.html
     → Mỗi bài: extract Q&A content + link "Bài đọc" (toàn văn)

  2. TÁC GIẢ - TÁC PHẨM (toàn văn, không phân series)
     → loigiaihay.com/tac-gia-tac-pham-van-9-c1789.html
     → ~90 tác phẩm, mỗi trang có toàn văn + tiểu sử

  3. TÓM TẮT - BỐ CỤC (3 series)
     → /tom-tat-bo-cuc-van-9-*-c*.html

  4. BÀI ĐỌC TAB
     → Từ mỗi trang soạn bài, extract link /van-ban-* nếu có

Output: JSONL files
  - lesson_guide_v2.jsonl    (soạn bài Q&A)
  - literature_text_v2.jsonl  (toàn văn)
  - summary_v2.jsonl          (tóm tắt)

Usage:
  python3 crawl_ngu_van_full.py [--resume]
"""

import json, re, time, asyncio, argparse, logging
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ──────────────────── CONFIG ────────────────────────────────────────────────
BASE    = "https://loigiaihay.com"
DATA    = Path("/home/namnx/knowledgeforptalk/rag_edu/data/grade9_v2")
LOG_F   = DATA / "crawl_v2.log"
DELAY   = 0.5   # seconds between requests
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Accept-Language": "vi-VN,vi;q=0.9"}

CATEGORY_MAP = {
    "CTST": {
        "soan": "/soan-van-9-chan-troi-sang-tao-c1743.html",
        "tomtat": "/tom-tat-bo-cuc-van-9-chan-troi-sang-tao-c1801.html",
    },
    "KNTT": {
        "soan": "/soan-van-9-ket-noi-tri-thuc-c1740.html",
        "tomtat": "/tom-tat-bo-cuc-van-9-ket-noi-tri-thuc-c1799.html",
    },
    "CD": {
        "soan": "/soan-van-9-canh-dieu-c1742.html",
        "tomtat": "/tom-tat-bo-cuc-van-9-canh-dieu-c1800.html",
    },
}
TAC_PHAM_URL = "/tac-gia-tac-pham-van-9-c1789.html"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ──────────────────── HELPERS ────────────────────────────────────────────────

def get(url: str, retries=3) -> BeautifulSoup | None:
    """Fetch URL và trả về BeautifulSoup, None nếu lỗi."""
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            log.warning(f"Attempt {i+1}/{retries} failed for {url}: {e}")
            time.sleep(1.5)
    return None


def abs_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return BASE + href if href.startswith("/") else BASE + "/" + href


def clean_text(txt: str, max_chars=15000) -> str:
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r"[ \t]+", " ", txt)
    return txt.strip()[:max_chars]


def get_cat_links(cat_url: str) -> list[tuple[str, str]]:
    """Lấy tất cả article links từ category page (có pagination)."""
    links = []
    seen = set()
    page_url = cat_url
    page_num = 1
    while page_url:
        soup = get(page_url)
        if not soup:
            break
        # Extract article links
        found = False
        for a in soup.find_all("a", href=True):
            href = a["href"]
            txt  = a.get_text(strip=True)
            if re.search(r"-a\d{4,}\.html", href) and len(txt) > 5:
                full = abs_url(href)
                if full not in seen:
                    seen.add(full)
                    links.append((txt, full))
                    found = True
        log.info(f"  Page {page_num}: {len(links)} links so far")
        # Pagination: tìm link "Trang tiếp"
        next_a = soup.find("a", string=re.compile(r"Trang tiếp|Next|»", re.I))
        if next_a and next_a.get("href"):
            next_href = next_a["href"]
            page_url = abs_url(next_href)
            page_num += 1
        else:
            break
        time.sleep(DELAY)
    return links


# ──────────────────── PARSER: SOẠN BÀI ────────────────────────────────────

def parse_soan_bai(url: str, series: str) -> dict | None:
    soup = get(url)
    if not soup:
        return None

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""
    if not title:
        return None

    # Extract "Bài đọc" / van-ban link
    bai_doc_url = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        atxt = a.get_text(strip=True).lower()
        if "/van-ban-" in href and ("bài đọc" in atxt or "văn bản" in atxt or "xem chi tiết" in atxt):
            bai_doc_url = abs_url(href)
            break
    # Fallback: bất kỳ /van-ban- link nào trong page
    if not bai_doc_url:
        for a in soup.find_all("a", href=True):
            if "/van-ban-" in a["href"]:
                bai_doc_url = abs_url(a["href"])
                break

    # Extract Q&A content từ box-content
    box = soup.find("div", id="box-content") or soup.find("div", class_="content_box")
    content = ""
    if box:
        # Extract Q&A pairs
        qas = []
        questions = box.find_all(["div","p"], class_=re.compile(r"box-question|question|cau-hoi", re.I))
        if questions:
            for q in questions:
                q_txt = q.get_text(separator="\n", strip=True)
                # Find answer sibling
                ans = q.find_next_sibling(class_=re.compile(r"explanation|answer|giai", re.I))
                a_txt = ans.get_text(separator="\n", strip=True) if ans else ""
                if q_txt:
                    qas.append(f"Q: {q_txt}\nA: {a_txt}")
            content = "\n\n".join(qas)
        if not content:
            content = box.get_text(separator="\n")

    content = clean_text(content)
    if len(content) < 50:
        return None

    return {
        "type": "lesson_guide",
        "title": title,
        "content": content,
        "bai_doc_url": bai_doc_url,
        "url": url,
        "series": series,
        "grade": 9,
        "subject": "Ngữ Văn",
        "crawled_at": datetime.now().isoformat(),
    }


# ──────────────────── PARSER: TÁC GIẢ - TÁC PHẨM (toàn văn) ──────────────

def parse_tac_pham(url: str, series: str = "") -> dict | None:
    """Parse trang tác giả/tác phẩm — chứa toàn văn + tiểu sử."""
    soup = get(url)
    if not soup:
        return None

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""
    if not title:
        return None

    box = soup.find("div", id="box-content") or soup.find("div", class_="content_box")
    if not box:
        return None

    raw = box.get_text(separator="\n")

    # Extract author từ title
    author_m = re.search(r"\(([^)]{3,60})\)", title)
    author = author_m.group(1) if author_m else ""

    # Tìm phần toàn văn — thường sau "Văn bản:" hoặc "Tác phẩm:" heading
    sections = {}
    current_sec = "intro"
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Section headers
        if re.match(r"^(I+\.?\s+|[1-9]\.\s+)?(Toàn văn|Văn bản|Tác phẩm|Nội dung|Bố cục|Tóm tắt|Tiểu sử|Tác giả)", line, re.I):
            key = re.sub(r"^(I+\.?\s+|[1-9]\.\s+)", "", line).lower().split()[0]
            current_sec = key
            sections.setdefault(current_sec, [])
        else:
            sections.setdefault(current_sec, []).append(line)

    # Ưu tiên: toàn văn > văn bản > nội dung > tóm tắt
    full_text = ""
    for key in ["toàn", "văn", "nội", "tóm", "intro"]:
        for sec_key, lines in sections.items():
            if sec_key.startswith(key):
                full_text = "\n".join(lines).strip()
                break
        if full_text:
            break
    if not full_text:
        full_text = clean_text(raw)

    if len(full_text) < 30:
        return None

    return {
        "type": "literature_text",
        "title": title,
        "author": author,
        "full_text": clean_text(full_text),
        "raw_full": clean_text(raw, 5000),  # toàn bộ page text để fallback
        "url": url,
        "series": series,
        "grade": 9,
        "subject": "Ngữ Văn",
        "crawled_at": datetime.now().isoformat(),
    }


# ──────────────────── PARSER: VAN BAN (Bài đọc) ───────────────────────────

def parse_van_ban(url: str, series: str = "") -> dict | None:
    """Parse trang /van-ban-* — chứa toàn văn tác phẩm."""
    soup = get(url)
    if not soup:
        return None

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""
    if not title:
        return None

    box = soup.find("div", id="box-content") or soup.find("div", class_="content_box")
    if not box:
        return None

    raw = box.get_text(separator="\n")

    # Bỏ phần hỏi đáp phía sau văn bản
    # Pattern: phần sau [...] là câu hỏi, lấy phần trước (toàn văn)
    # Hoặc tìm heading "Câu hỏi" để cắt
    text_part = raw
    for marker in ["Câu 1", "Câu hỏi", "Trả lời câu hỏi", "Soạn bài", "👉"]:
        idx = text_part.find(marker)
        if idx > 200:  # Đảm bảo có ít nhất 200 chars toàn văn
            text_part = text_part[:idx]
            break

    author_m = re.search(r"\(([^)]{3,60})\)", title)
    full_text = clean_text(text_part)

    if len(full_text) < 50:
        return None

    return {
        "type": "literature_text",
        "title": title,
        "author": author_m.group(1) if author_m else "",
        "full_text": full_text,
        "url": url,
        "series": series,
        "grade": 9,
        "subject": "Ngữ Văn",
        "crawled_at": datetime.now().isoformat(),
    }


# ──────────────────── PARSER: TÓM TẮT ─────────────────────────────────────

def parse_tom_tat(url: str, series: str) -> dict | None:
    soup = get(url)
    if not soup:
        return None

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""
    if not title:
        return None

    box = soup.find("div", id="box-content") or soup.find("div", class_="content_box")
    if not box:
        return None

    content = clean_text(box.get_text(separator="\n"), 6000)
    if len(content) < 50:
        return None

    return {
        "type": "summary",
        "title": title,
        "content": content,
        "url": url,
        "series": series,
        "grade": 9,
        "subject": "Ngữ Văn",
        "crawled_at": datetime.now().isoformat(),
    }


# ──────────────────── MAIN ──────────────────────────────────────────────────

def load_done(path: Path) -> set[str]:
    done = set()
    if path.exists():
        for line in path.open():
            try:
                done.add(json.loads(line)["url"])
            except Exception:
                pass
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="Skip already crawled URLs")
    args = parser.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)

    lesson_f  = DATA / "lesson_guide_v2.jsonl"
    lit_f     = DATA / "literature_text_v2.jsonl"
    summ_f    = DATA / "summary_v2.jsonl"

    done_lesson  = load_done(lesson_f)  if args.resume else set()
    done_lit     = load_done(lit_f)     if args.resume else set()
    done_summ    = load_done(summ_f)    if args.resume else set()

    stats = {"lesson": 0, "lit": 0, "summ": 0, "skip": 0, "fail": 0}

    with open(lesson_f, "a") as lf, open(lit_f, "a") as litf, open(summ_f, "a") as sf:

        # ══════════════════════════════════════════════════════════
        # PHASE 1: SOẠN BÀI (3 series) + extract Bài đọc links
        # ══════════════════════════════════════════════════════════
        bai_doc_queue: list[tuple[str, str]] = []  # (url, series)

        for series, cats in CATEGORY_MAP.items():
            log.info(f"\n{'='*60}")
            log.info(f"[{series}] Crawling SOẠN BÀI: {cats['soan']}")
            links = get_cat_links(BASE + cats["soan"])
            log.info(f"  → {len(links)} articles found")

            for txt, url in links:
                time.sleep(DELAY)
                if url in done_lesson:
                    stats["skip"] += 1
                    continue
                doc = parse_soan_bai(url, series)
                if doc:
                    lf.write(json.dumps(doc, ensure_ascii=False) + "\n")
                    lf.flush()
                    stats["lesson"] += 1
                    # Queue Bài đọc URL
                    if doc.get("bai_doc_url") and doc["bai_doc_url"] not in done_lit:
                        bai_doc_queue.append((doc["bai_doc_url"], series))
                    log.info(f"  ✅ [{series}] {doc['title'][:55]}")
                else:
                    stats["fail"] += 1
                    log.warning(f"  ❌ FAIL: {url}")

        # ══════════════════════════════════════════════════════════
        # PHASE 2: BÀI ĐỌC (van-ban) từ soạn bài
        # ══════════════════════════════════════════════════════════
        log.info(f"\n{'='*60}")
        log.info(f"[VAN BAN] Crawling {len(bai_doc_queue)} Bài đọc URLs from soạn bài")
        seen_vb = set()
        for url, series in bai_doc_queue:
            if url in done_lit or url in seen_vb:
                continue
            seen_vb.add(url)
            time.sleep(DELAY)
            doc = parse_van_ban(url, series)
            if doc:
                litf.write(json.dumps(doc, ensure_ascii=False) + "\n")
                litf.flush()
                stats["lit"] += 1
                log.info(f"  ✅ [VB/{series}] {doc['title'][:55]} | {len(doc['full_text'])} chars")
            else:
                stats["fail"] += 1

        # ══════════════════════════════════════════════════════════
        # PHASE 3: TÁC GIẢ - TÁC PHẨM (90 tác phẩm, toàn văn)
        # ══════════════════════════════════════════════════════════
        log.info(f"\n{'='*60}")
        log.info(f"[TÁC PHẨM] Crawling tac-gia-tac-pham page...")
        tp_links = get_cat_links(BASE + TAC_PHAM_URL)
        log.info(f"  → {len(tp_links)} tác phẩm links found")

        for txt, url in tp_links:
            time.sleep(DELAY)
            if url in done_lit or url in seen_vb:
                stats["skip"] += 1
                continue
            doc = parse_tac_pham(url, "")   # series = "" vì page này cross-series
            if doc:
                litf.write(json.dumps(doc, ensure_ascii=False) + "\n")
                litf.flush()
                stats["lit"] += 1
                log.info(f"  ✅ [TP] {doc['title'][:55]} | {len(doc['full_text'])} chars")
            else:
                # Fallback: thử parse như van-ban
                doc2 = parse_van_ban(url, "")
                if doc2:
                    litf.write(json.dumps(doc2, ensure_ascii=False) + "\n")
                    litf.flush()
                    stats["lit"] += 1
                else:
                    stats["fail"] += 1
                    log.warning(f"  ❌ FAIL TP: {url}")

        # ══════════════════════════════════════════════════════════
        # PHASE 4: TÓM TẮT - BỐ CỤC (3 series)
        # ══════════════════════════════════════════════════════════
        for series, cats in CATEGORY_MAP.items():
            log.info(f"\n{'='*60}")
            log.info(f"[{series}] Crawling TÓM TẮT: {cats['tomtat']}")
            links = get_cat_links(BASE + cats["tomtat"])
            log.info(f"  → {len(links)} bài found")

            for txt, url in links:
                time.sleep(DELAY)
                if url in done_summ:
                    stats["skip"] += 1
                    continue
                doc = parse_tom_tat(url, series)
                if doc:
                    sf.write(json.dumps(doc, ensure_ascii=False) + "\n")
                    sf.flush()
                    stats["summ"] += 1
                    log.info(f"  ✅ [{series}] Tóm tắt: {doc['title'][:55]}")
                else:
                    stats["fail"] += 1

    # Summary
    log.info(f"\n{'='*60}")
    log.info(f"DONE!")
    log.info(f"  LessonGuide:    {stats['lesson']} mới")
    log.info(f"  LiteratureText: {stats['lit']} mới")
    log.info(f"  Summary:        {stats['summ']} mới")
    log.info(f"  Skip (resume):  {stats['skip']}")
    log.info(f"  Fail:           {stats['fail']}")
    log.info(f"\nFiles:")
    for p in [lesson_f, lit_f, summ_f]:
        if p.exists():
            n = sum(1 for _ in open(p))
            log.info(f"  {p.name}: {n} records")


if __name__ == "__main__":
    main()
