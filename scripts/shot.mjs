#!/usr/bin/env node
// 웹 페이지 스크린샷을 PNG로 저장한다.
//
// 사용법:
//   node scripts/shot.mjs <url> <out.png> [옵션]
// 옵션:
//   --mobile            휴대폰 화면(390x844)으로 찍음. 기본은 데스크톱(1280x800)
//   --full              페이지 전체를 찍음 (기본은 첫 화면)
//   --selector <css>    해당 요소만 찍음
//   --click <css>       찍기 전에 클릭 (여러 번 줄 수 있음)
//   --wait <ms>         페이지가 뜬 뒤 기다릴 시간 (기본 1500)
import { chromium, devices } from "playwright";

const [url, out, ...rest] = process.argv.slice(2);
if (!url || !out) {
  console.error("사용법: node scripts/shot.mjs <url> <out.png> [--mobile] [--full] [--selector css] [--click css] [--wait ms]");
  process.exit(1);
}

const opts = { mobile: false, full: false, selector: null, clicks: [], wait: 1500 };
for (let i = 0; i < rest.length; i++) {
  const a = rest[i];
  if (a === "--mobile") opts.mobile = true;
  else if (a === "--full") opts.full = true;
  else if (a === "--selector") opts.selector = rest[++i];
  else if (a === "--click") opts.clicks.push(rest[++i]);
  else if (a === "--wait") opts.wait = Number(rest[++i]);
}

const browser = await chromium.launch();
try {
  const context = await browser.newContext(
    opts.mobile
      ? { ...devices["iPhone 13"], deviceScaleFactor: 3 }
      : { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 },
  );
  const page = await context.newPage();
  const res = await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
  if (!res || !res.ok()) throw new Error(`페이지를 열지 못했습니다: ${res ? res.status() : "응답 없음"}`);
  for (const sel of opts.clicks) {
    await page.click(sel, { timeout: 10000 });
    await page.waitForLoadState("networkidle").catch(() => {});
  }
  await page.waitForTimeout(opts.wait);
  const target = opts.selector ? page.locator(opts.selector).first() : page;
  await target.screenshot({ path: out, ...(opts.selector ? {} : { fullPage: opts.full }) });
  console.log(JSON.stringify({ saved: out, final_url: page.url(), title: await page.title() }));
} finally {
  await browser.close();
}
