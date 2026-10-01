"""
run_tests.py  (ver1 - 2026.09.28)
dist/ 웹앱을 실제 브라우저(Chromium)로 열어 핵심 흐름을 검사한다.
빌드 후, 템플릿이나 build.py 를 고친 뒤에 실행한다.

필요 패키지: pip install playwright  →  python -m playwright install chromium
기록(localStorage)은 테스트용 임시 브라우저에만 남으므로 실제 기록에 영향 없음.
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("  통과 " if ok else "  실패 ") + name + (f"  ({detail})" if detail and not ok else ""))


def url(fn):
    return "file:///" + os.path.join(DIST, fn).replace("\\", "/").lstrip("/")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 420, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        # 1. 인덱스
        await pg.goto(url("index.html"))
        cards = await pg.locator(".round-card").count()
        check("인덱스에 회차 카드 표시", cards > 0, f"{cards}개")
        first = await pg.locator(".round-card").first.get_attribute("href")
        check("최신 회차가 맨 앞", first is not None, first or "")

        # 2. 모든 회차 데이터 로드 + 이미지
        for a in await pg.locator(".round-card").all():
            href = await a.get_attribute("href")
            page2 = await b.new_page()
            await page2.goto(url(href))
            n = await page2.evaluate("(window.ROUND_DATA||{problems:[]}).problems.length")
            check(f"{href} 데이터 50문항", n == 50, f"{n}")
            await page2.click("text=1~25번")
            try:
                await page2.wait_for_function("(()=>{const i=document.querySelector('.qimg img');return !!i && i.complete && i.naturalWidth>0})()", timeout=5000)
                ok = True
            except Exception:
                ok = False
            check(f"{href} 1번 이미지 표시", ok)
            await page2.close()

        # 3. 연습 흐름 (첫 회차)
        await pg.goto(url(first))
        await pg.evaluate("localStorage.clear()")
        await pg.reload()
        await pg.click("text=1~25번")
        check("연습 모드에 시계 없음", await pg.locator("#clock").count() == 0)
        ans = await pg.evaluate("ROUND_DATA.problems[0].a")
        await pg.click(f".bub >> nth={ans - 1}")
        check("정답 선택 시 A·B만 활성", await pg.is_enabled('.rxb[data-k="B"]') and await pg.is_disabled('.rxb[data-k="C"]'))
        await pg.click('.rxb[data-k="B"]')
        check("B 선택 후 기록 전 다음 불가", await pg.is_disabled("#nextBtn"))
        await pg.fill("#note", "테스트 근거")
        check("기록 후 다음 가능", await pg.is_enabled("#nextBtn"))
        await pg.click("#nextBtn")
        ans2 = await pg.evaluate("ROUND_DATA.problems[1].a")
        await pg.click(f".bub >> nth={ans2 % 5}")                 # 일부러 오답
        check("오답 선택 시 C·D만 활성", await pg.is_enabled('.rxb[data-k="C"]') and await pg.is_disabled('.rxb[data-k="A"]'))
        await pg.click('.rxb[data-k="A"]', force=True)
        await pg.click('.rxb[data-k="D"]')
        await pg.fill("#note", "핵심 키워드")
        await pg.click("text=그만하기")
        await pg.wait_for_timeout(300)
        out = await pg.input_value("#out")
        check("기록 텍스트에 B·D 항목", "B |" in out and "D |" in out)
        check("연습 기록에 시간 줄 없음", "시간" not in out.splitlines()[1])

        # 4. 이어하기 저장
        await pg.click("text=처음으로")
        await pg.click("text=80분 실전 시작")
        await pg.click(".bub >> nth=0")
        await pg.reload()
        check("새로고침 후 이어서 풀기 표시", await pg.locator("text=이어서 풀기").count() == 1)
        await pg.click("text=이어서 풀기")
        check("실전 시계 표시", await pg.locator("#clock").count() == 1)
        await pg.click("text=제출")
        await pg.wait_for_timeout(300)
        check("제출 후 번호판 표시", await pg.locator(".sheet .cell").count() == 50)

        check("스크립트 오류 없음", not errs, "; ".join(errs))
        await b.close()
    print(f"\n{sum(results)}/{len(results)} 통과")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
