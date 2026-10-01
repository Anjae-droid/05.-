"""
import_explanations.py  (ver1 - 2026.09.28)
inbox/해설/ 의 해설 PDF 를 읽어 data/<회차>/문항.csv 의 해설 칸에 넣는다.

  - 'NN회 NN번' 을 기준으로 해설을 나눈다. 앞의 큰 번호(1), 2) ...)는 무시한다.
  - 해설 칸이 이미 채워진 문항은 건너뛴다 (--force 로 덮어쓰기).
  - a. / i. / 1. 목록 기호는 들여쓰기 불릿으로 바꾼다.
  - 문항.csv 가 없는 회차의 해설은 반영하지 않고 목록만 보여 준다.

필요 패키지: pip install pymupdf
"""
import csv
import os
import re
import shutil
import sys

try:
    import pymupdf as fitz
except ImportError:
    print("패키지가 없습니다. 먼저 실행하세요:  pip install pymupdf")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "inbox", "해설")
DONE = os.path.join(INBOX, "done")
DATA = os.path.join(ROOT, "data")

HEAD = re.compile(r"(\d{2,3})\s*회\s*(\d{1,2})\s*번")
ROMAN = r"(?:i{1,3}|iv|v|vi{1,3}|ix|x)"


def clean_block(raw):
    raw = re.sub(r"\s*\d{1,2}\)\s*$", "", raw.strip())          # 다음 항목의 큰 번호 꼬리 제거
    raw = re.sub(rf"(?<!\n)(?=\b(?:[a-h]|{ROMAN}|\d{{1,2}})[.)]\s)", "\n", raw)  # 붙어 버린 목록 기호 분리
    out = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(rf"^({ROMAN})[.)]\s*(.*)$", s)
        if m:
            out.append("  - " + m.group(2)); continue
        m = re.match(r"^([a-h])[.)]\s*(.*)$", s)
        if m:
            out.append("• " + m.group(2)); continue
        m = re.match(r"^(\d{1,2})[.)]\s*(.*)$", s)
        if m:
            out.append("    · " + m.group(2)); continue
        if out and not s.startswith(("(", "-", "※")) and out[-1] and not out[-1].endswith(":"):
            out[-1] += " " + s                                    # 줄바꿈으로 끊긴 문장 잇기
        else:
            out.append(s)
    return "\n".join(out).strip()


def parse_pdf(path):
    doc = fitz.open(path)
    text = "\n".join(pg.get_text() for pg in doc)
    doc.close()
    marks = list(HEAD.finditer(text))
    items = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end]
        title = ""
        tm = re.match(r"^\s*(\([^)]*\)|-\s*[^\n]*)", body)   # (관등제도) 또는 - 고려시대 문제
        if tm:
            title = tm.group(1).strip("()- ").strip()
            body = body[tm.end():]
        exp = clean_block(body)
        if title:
            exp = f"[{title}]\n{exp}" if exp else title
        items[(int(m.group(1)), int(m.group(2)))] = exp
    return items


def main():
    force = "--force" in sys.argv
    os.makedirs(INBOX, exist_ok=True)
    pdfs = [f for f in os.listdir(INBOX) if f.lower().endswith(".pdf")]
    if not pdfs:
        print("inbox/해설 폴더에 PDF 가 없습니다.")
        return 0
    found = {}
    for f in pdfs:
        items = parse_pdf(os.path.join(INBOX, f))
        print(f"  {f}: 해설 {len(items)}개 인식")
        found.update(items)

    by_round = {}
    for (r, n), x in found.items():
        by_round.setdefault(r, {})[n] = x
    for r in sorted(by_round):
        path = os.path.join(DATA, str(r), "문항.csv")
        if not os.path.exists(path):
            print(f"  {r}회: 문항.csv 없음 - 반영 안 함 {sorted(by_round[r])}")
            continue
        with open(path, encoding="utf-8-sig", newline="") as fp:
            rows = list(csv.DictReader(fp))
        put, skip = [], []
        for row in rows:
            n = int(row["번호"])
            if n in by_round[r]:
                if (row.get("해설") or "").strip() and not force:
                    skip.append(n)
                else:
                    row["해설"] = by_round[r][n]
                    put.append(n)
        with open(path, "w", encoding="utf-8-sig", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=["번호", "정답", "배점", "시대", "검토필요", "해설"])
            w.writeheader()
            w.writerows(rows)
        print(f"  {r}회: 반영 {len(put)}개 {put}" + (f" / 기존 해설 있어 건너뜀 {skip}" if skip else ""))

    os.makedirs(DONE, exist_ok=True)
    for f in pdfs:
        shutil.move(os.path.join(INBOX, f), os.path.join(DONE, f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
