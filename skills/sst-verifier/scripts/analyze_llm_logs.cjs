const { chromium } = require('playwright');

async function analyze() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  console.log('[*] Navigating to LLM Logs page...');
  await page.goto('http://localhost:8000/llm-logs', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  const results = await page.evaluate(() => {
    const report = {
      sidebar: {
        buttonsFound: 0,
        buttonStyles: [],
        firstButtonText: ""
      },
      detailArea: {
        initialState: "unknown",
        afterClickState: "unknown"
      },
      errors: []
    };

    // Listen for JS errors
    window.onerror = (m) => report.errors.push(m);

    const buttons = Array.from(document.querySelectorAll('button')).filter(b => b.innerText.includes('APP ID'));
    report.sidebar.buttonsFound = buttons.length;

    if (buttons.length > 0) {
      const btn = buttons[0];
      const style = window.getComputedStyle(btn);
      const title = btn.querySelector('div.text-xs.font-bold, div.text-slate-300'); // Check both old and new classes
      
      report.sidebar.buttonStyles.push({
        bg: style.backgroundColor,
        color: style.color,
        titleColor: title ? window.getComputedStyle(title).color : 'N/A'
      });
      report.sidebar.firstButtonText = btn.innerText;
    }

    const detailTitle = document.querySelector('h3.text-base, h3.font-bold');
    report.detailArea.initialState = detailTitle ? "shown: " + detailTitle.innerText : "empty_placeholder";

    return report;
  });

  console.log('--- Initial State Report ---');
  console.log(JSON.stringify(results, null, 2));

  // Perform Click
  if (results.sidebar.buttonsFound > 0) {
    console.log('[*] Clicking first log entry...');
    await page.click('button:has-text("APP ID")');
    await page.waitForTimeout(1000);

    const afterClick = await page.evaluate(() => {
      const detailTitle = document.querySelector('div.text-base.font-bold, h3.font-bold');
      const chatBubbles = document.querySelectorAll('div.rounded-2xl');
      return {
        detailShown: !!detailTitle,
        title: detailTitle?.innerText,
        bubbleCount: chatBubbles.length
      };
    });
    console.log('--- After Click Report ---');
    console.log(JSON.stringify(afterClick, null, 2));
  }

  await browser.close();
}

analyze();
