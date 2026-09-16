import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const url = process.env.ASSISTANT_URL ||
  'https://aigc.zygcdata.com/workspace/chat/assistant/auth/06e8a9fe6986474f8599fc18e38bc37c';
const headless = process.env.HEADLESS === '1';
const outDir = path.resolve(process.env.OUT_DIR || './artifacts/public-assistant');
const cases = [
  { id: 'T01', text: '我开奶茶店，每天300块，想加微信' },
  { id: 'T04', text: '我想投广告' },
  { id: 'T05', text: '什么时候投效果最好' },
  { id: 'T06', text: '保证我一个月卖1000单' },
  { id: 'T10', text: '用全网最低价写标题' },
  { id: 'T13', text: '帮我查最近的教育培训广告政策' },
  { id: 'T14', text: '我卖咖啡，帮我看看竞品卖点和价格' },
  { id: 'T15', text: '把刚才预算到转化画成漏斗图' },
];

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function findComposer(page) {
  const candidates = [
    page.locator('textarea').last(),
    page.locator('[contenteditable="true"]').last(),
    page.locator('input[type="text"]').last(),
  ];
  for (const locator of candidates) {
    if (await locator.count() && await locator.isVisible().catch(() => false)) return locator;
  }
  throw new Error('找不到输入框。请用 HEADLESS=0 打开页面后检查 DOM，并按平台实际控件补充选择器。');
}

async function messageCount(page) {
  const selectors = [
    '[data-message-author-role]',
    '[data-testid*="message"]',
    '.message-content',
    'main article',
  ];
  for (const selector of selectors) {
    const count = await page.locator(selector).count().catch(() => 0);
    if (count > 0) return count;
  }
  return 0;
}

async function lastVisibleText(page) {
  const selectors = [
    '[data-message-author-role="assistant"]',
    '[data-testid*="message"]',
    '.message-content',
    'main article',
  ];
  for (const selector of selectors) {
    const all = page.locator(selector);
    const count = await all.count().catch(() => 0);
    let loc = null;
    for (let i = count - 1; i >= 0; i -= 1) {
      const candidate = all.nth(i);
      if (await candidate.isVisible().catch(() => false)) {
        loc = candidate;
        break;
      }
    }
    if (!loc) continue;
    return (await loc.innerText().catch(() => '')).trim();
  }
  return '';
}

async function waitForReply(page, beforeCount, timeoutMs = 90000) {
  const started = Date.now();
  let last = '';
  let stableSince = 0;
  while (Date.now() - started < timeoutMs) {
    const count = await messageCount(page);
    const current = await lastVisibleText(page);
    if (count > beforeCount && current) {
      if (current === last) {
        if (!stableSince) stableSince = Date.now();
        if (Date.now() - stableSince > 1500) return current;
      } else {
        last = current;
        stableSince = 0;
      }
    }
    await sleep(500);
  }
  throw new Error(`等待助手回答超时（${timeoutMs}ms）`);
}

async function main() {
  await fs.mkdir(outDir, { recursive: true });
  const browser = await chromium.launch({ headless });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const results = [];

  try {
    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
    await page.screenshot({ path: path.join(outDir, '00-loaded.png'), fullPage: true });
    await page.close();

    for (const item of cases) {
      // 每道题单独打开公开链接，避免上一题的上下文污染本题结果。
      const testPage = await context.newPage();
      await testPage.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await testPage.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
      const composer = await findComposer(testPage);
      const before = await messageCount(testPage);
      await composer.fill(item.text);
      await composer.press('Enter');
      const answer = await waitForReply(testPage, before);
      const screenshot = path.join(outDir, `${item.id}.png`);
      await testPage.screenshot({ path: screenshot, fullPage: true });
      results.push({ id: item.id, question: item.text, answer, screenshot, status: 'captured' });
      await testPage.close();
      await sleep(2500); // 低频发送，避免触发平台限流
    }
  } catch (error) {
    results.push({ status: 'error', error: String(error), url });
    // 错误截图在循环内单独保存；页面可能已在失败前关闭，因此不强制截图。
    process.exitCode = 1;
  } finally {
    await fs.writeFile(path.join(outDir, 'results.json'), JSON.stringify({ url, results }, null, 2));
    await browser.close();
  }
}

main();
