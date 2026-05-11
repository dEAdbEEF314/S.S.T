const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function capture() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const outputDir = path.join(process.cwd(), 'ui_verification');
  
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir);
  }

  console.log('[*] Capturing UI Screenshots...');

  const pages = [
    { name: 'dashboard', url: 'http://localhost:8000/' },
    { name: 'archive', url: 'http://localhost:8000/archive' },
    { name: 'review', url: 'http://localhost:8000/review' },
    { name: 'llm-logs', url: 'http://localhost:8000/llm-logs' }
  ];

  for (const p of pages) {
    try {
      console.log(`[*] Accessing ${p.name}...`);
      await page.goto(p.url, { waitUntil: 'networkidle' });
      // Wait a bit for potential animations or late data
      await page.waitForTimeout(2000);
      
      const screenshotPath = path.join(outputDir, `${p.name}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: true });
      console.log(`[+] Saved: ${screenshotPath}`);

      // Special case: Click the first log if we are on llm-logs page
      if (p.name === 'llm-logs') {
        console.log('[*] Clicking first log entry...');
        const logButton = await page.$('button.w-full.text-left');
        if (logButton) {
          await logButton.click();
          await page.waitForTimeout(1000); // Wait for transition
          const detailPath = path.join(outputDir, 'llm-log-detail.png');
          await page.screenshot({ path: detailPath, fullPage: true });
          console.log(`[+] Saved: ${detailPath}`);
        } else {
          console.log('[!] No log entries found to click.');
        }
      }
    } catch (e) {
      console.error(`[-] Failed to capture ${p.name}: ${e.message}`);
    }
  }

  await browser.close();
}

capture();
