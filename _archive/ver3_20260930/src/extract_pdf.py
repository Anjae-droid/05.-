"""
extract_pdf.py  (ver1 - 2026.09.28)
inbox/ 에 넣은 시험지 PDF(문제지 + 정답표)를 data/<회차>/ 로 추출한다.

  - 파일명에 'NN회' 가 있어야 회차를 인식한다.
  - 파일명에 '문제' 가 있으면 문제지, '정답'/'답지'/'답안' 이 있으면 정답표.
  - 텍스트 레이어가 없는 스캔(이미지) PDF 는 문항 위치를 못 찾으므로 건너뛴다.
  - 이미 data/<회차>/문항.csv 가 있으면 덮어쓰지 않는다 (--force 로 강제).
  - 시대는 키워드로 자동 분류하고, 애매한 문항은 검토필요=Y 로 표시한다.
    엑셀로 문항.csv 를 열어 시대를 확인·수정한 뒤 검토필요 칸을 비우면 된다.

필요 패키지: pip install pymupdf pillow
"""
import csv
import io
import os
import re
import shutil
import sys

try:
    import pymupdf as fitz
    from PIL import Image
except ImportError:
    print("패키지가 없습니다. 먼저 실행하세요:  pip install pymupdf pillow")
    sys.exit(1)

from era_keywords import classify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "inbox")
DONE = os.path.join(INBOX, "done")
DATA = os.path.join(ROOT, "data")

# 페이지 좌표 (pt). 70·71·72·75·76·77회 문제지 기준 (729 x 1032 pt, 2단 편집)
LEFT_COL_END = 374
RIGHT_COL_END = 728
PAGE_BOTTOM = 985
DPI = 200
IMG_WIDTH = 700
JPEG_Q = 72
CIRCLED = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}


def find_problems(doc):
    found = {}
    for pno in range(len(doc)):
        for block in doc[pno].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    m = re.match(r"^(\d{1,2})\.$", span["text"].strip())
                    if m and span["size"] > 12:
                        n = int(m.group(1))
                        if 1 <= n <= 50 and n not in found:
                            found[n] = {"n": n, "page": pno, "x": span["bbox"][0], "y": span["bbox"][1]}
    return [found[k] for k in sorted(found)]


def region(p, allp):
    nxt = [q["y"] for q in allp if q["page"] == p["page"] and abs(q["x"] - p["x"]) < 20 and q["y"] > p["y"]]
    x0 = p["x"] - 8
    x1 = LEFT_COL_END if p["x"] < 200 else RIGHT_COL_END - 5
    y0 = p["y"] - 8
    y1 = (min(nxt) - 8) if nxt else PAGE_BOTTOM
    return fitz.Rect(x0, y0, x1, y1)


def parse_answers(path):
    doc = fitz.open(path)
    text = "".join(pg.get_text() for pg in doc)
    doc.close()
    tokens = re.findall(r"[①②③④⑤]|\d+", text)
    ans, pts = {}, {}
    i = 0
    while i < len(tokens) - 2:
        t1, t2, t3 = tokens[i], tokens[i + 1], tokens[i + 2]
        if t2 in CIRCLED and t1 not in CIRCLED and t3 not in CIRCLED:
            n, p = int(t1), int(t3)
            if 1 <= n <= 50 and 1 <= p <= 3 and n not in ans:
                ans[n], pts[n] = CIRCLED[t2], p
                i += 3
                continue
        i += 1
    return ans, pts


def extract_round(r, qpath, apath, force):
    out = os.path.join(DATA, str(r))
    csv_path = os.path.join(out, "문항.csv")
    if os.path.exists(csv_path) and not force:
        print(f"  {r}회: 이미 있음 (data/{r}/문항.csv). 다시 만들려면 --force")
        return False

    ans, pts = parse_answers(apath)
    if len(ans) != 50 or sum(pts.values()) != 100:
        print(f"  {r}회: 정답표 파싱 실패 (정답 {len(ans)}/50, 배점 합 {sum(pts.values())})")
        return False

    doc = fitz.open(qpath)
    probs = find_problems(doc)
    if len(probs) != 50:
        miss = sorted(set(range(1, 51)) - {p["n"] for p in probs})
        if not probs:
            print(f"  {r}회: 문항 번호를 찾지 못했습니다. 텍스트 레이어 없는 스캔 PDF 로 보입니다 - 자동 추출 불가")
        else:
            print(f"  {r}회: 문항 번호 {len(probs)}/50 만 찾음 (누락 {miss}) - 레이아웃이 다른 시험지일 수 있음")
        doc.close()
        return False

    os.makedirs(os.path.join(out, "img"), exist_ok=True)
    rows, review = [], []
    for p in probs:
        rect = region(p, probs)
        page = doc[p["page"]]
        pix = page.get_pixmap(clip=rect, dpi=DPI)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        if img.width > IMG_WIDTH:
            img = img.resize((IMG_WIDTH, int(img.height * IMG_WIDTH / img.width)), Image.LANCZOS)
        img.save(os.path.join(out, "img", f"q{p['n']:02d}.jpg"), "JPEG", quality=JPEG_Q, optimize=True)
        text = re.sub(r"\s+", " ", page.get_text(clip=rect))
        era, sure = classify(text)
        if not sure:
            review.append(p["n"])
        rows.append([p["n"], ans[p["n"]], pts[p["n"]], era, "" if sure else "Y", ""])
    doc.close()

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "정답", "배점", "시대", "검토필요", "해설"])
        w.writerows(rows)

    rounds_csv = os.path.join(DATA, "rounds.csv")
    have = set()
    if os.path.exists(rounds_csv):
        with open(rounds_csv, encoding="utf-8-sig", newline="") as f:
            have = {int(x["회차"]) for x in csv.DictReader(f)}
    if r not in have:
        new = not os.path.exists(rounds_csv)
        with open(rounds_csv, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["회차", "시행일"])
            w.writerow([r, ""])
    print(f"  {r}회: 50문항 추출 완료. 시대 검토필요 {len(review)}문항 {review}")
    print(f"        data/rounds.csv 에 {r}회 시행일을 적어 주세요 (비워도 동작함).")
    return True


def main():
    force = "--force" in sys.argv
    os.makedirs(INBOX, exist_ok=True)
    pdfs = [f for f in os.listdir(INBOX) if f.lower().endswith(".pdf")]
    if not pdfs:
        print("inbox 폴더에 PDF 가 없습니다. 문제지와 정답표 PDF 를 넣고 다시 실행하세요.")
        return 0
    groups = {}
    for f in pdfs:
        m = re.search(r"(\d{2,3})\s*회", f)
        if not m:
            print(f"  건너뜀: {f} (파일명에 'NN회' 없음)")
            continue
        r = int(m.group(1))
        g = groups.setdefault(r, {})
        if "문제" in f:
            g["q"] = f
        elif any(k in f for k in ("정답", "답지", "답안")):
            g["a"] = f
        else:
            print(f"  건너뜀: {f} (문제지/정답표 구분 불가 - 파일명에 '문제' 또는 '정답' 을 넣으세요)")
    for r in sorted(groups):
        g = groups[r]
        if "q" not in g or "a" not in g:
            print(f"  {r}회: 문제지와 정답표가 둘 다 있어야 합니다 (현재 {list(g.values())})")
            continue
        ok = extract_round(r, os.path.join(INBOX, g["q"]), os.path.join(INBOX, g["a"]), force)
        if ok:
            os.makedirs(DONE, exist_ok=True)
            for f in (g["q"], g["a"]):
                shutil.move(os.path.join(INBOX, f), os.path.join(DONE, f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
