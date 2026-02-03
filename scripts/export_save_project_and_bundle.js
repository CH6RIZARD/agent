#!/usr/bin/env node
/**
 * Export ALL chats from Claude.ai "save" project (no title filter).
 * Writes save_chats.md and save_chats.docx to saved/bundles/
 * Requires: playwright, docx, mammoth
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { Document, Packer, Paragraph, TextRun } = require('docx');

const OUT_DIR = path.join(__dirname, '..', 'saved', 'bundles');
const CLAUDE_URL = 'https://claude.ai';
const PROJECT_NAME = 'save';
const HEADED = process.env.HEADED !== '0';
// Your save project URL – set PROJECT_URL env var to override
const PROJECT_URL =
  process.env.PROJECT_URL || 'https://claude.ai/project/019c168d-1283-73af-9e7e-e4a83cf9cd41';
const LOGIN_WAIT_MS = parseInt(process.env.LOGIN_WAIT_MS || '15000', 10);

// Ensure output directory exists
fs.mkdirSync(OUT_DIR, { recursive: true });

// Claude selectors (from claude-chat-exporter)
const SELECTORS = {
  userMessage: '[data-testid="user-message"]',
  messageGroup: '.group',
  copyButton: 'button[data-testid="action-bar-copy"]',
  editButton: 'button[aria-label="Edit"]',
  editTextarea: 'textarea',
};

// Fallback: extract from DOM when copy-button method fails
const EXTRACT_DOM_FALLBACK = () => {
  const messages = [];
  // Prefer .group - captures both user and assistant; each group is one message
  const sel = ['.group', '[data-testid="user-message"]', '[data-testid="assistant-message"]', '[class*="Message"]', 'article'];
  let els = [];
  for (const s of sel) {
    els = Array.from(document.querySelectorAll(s));
    if (els.length > 0) break;
  }
  const getText = (el) => {
    if (!el) return '';
    const c = el.cloneNode(true);
    c.querySelectorAll?.('script, style, button, [aria-hidden]')?.forEach((n) => n.remove());
    return (c.innerText || c.textContent || '').trim();
  };
  els.forEach((el) => {
    const text = getText(el);
    const isUser =
      el.matches?.('[data-testid="user-message"]') ||
      el.querySelector?.('[data-testid="user-message"]') ||
      el.closest?.('[data-testid="user-message"]');
    if (text) messages.push({ role: isUser ? 'user' : 'assistant', text });
  });
  return messages;
};

// Extract chat using copy buttons (Claude's markdown) + edit buttons (human messages)
async function extractChatWithCopyButtons(page) {
  const humanMessages = [];
  const claudeResponses = [];

  await page.exposeFunction('__claudeCaptureCopy', (text) => {
    if (text && text.length > 20) claudeResponses.push(text);
  });

  await page.addInitScript(() => {
    const original = navigator.clipboard.writeText;
    navigator.clipboard.writeText = function (text) {
      if (typeof window.__claudeCaptureCopy === 'function' && text && text.length > 20) {
        window.__claudeCaptureCopy(text);
      }
      return original.apply(this, arguments);
    };
  });

  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // Scroll chat to load all messages (lazy loading)
  const chatArea = await page.$('[class*="overflow"], main, [role="main"], [class*="scroll"]');
  if (chatArea) {
    for (let i = 0; i < 10; i++) {
      await chatArea.evaluate((el) => el.scrollBy(0, 800));
      await page.waitForTimeout(500);
    }
    await chatArea.evaluate((el) => (el.scrollTop = 0));
    await page.waitForTimeout(1000);
  }
  await page.waitForTimeout(1000);

  // Extract human messages via Edit button (or fallback to innerText)
  const userEls = await page.$$(SELECTORS.userMessage);
  for (let i = 0; i < userEls.length; i++) {
    try {
      await userEls[i].hover();
      await page.waitForTimeout(100);
      const groupHandle = await userEls[i].evaluateHandle((el) => el.closest('.group'));
      const group = groupHandle.asElement();
      let content = '';
      if (group) {
        const editBtn =
          (await group.$(SELECTORS.editButton)) || (await group.$('button[aria-label*="Edit"]'));
        if (editBtn) {
          await editBtn.click();
          await page.waitForTimeout(200);
          const textarea = (await group.$('textarea')) || (await page.$(SELECTORS.editTextarea));
          content = textarea ? await textarea.inputValue() : '';
          await page.keyboard.press('Escape');
          await page.waitForTimeout(100);
        }
      }
      if (!content) content = await userEls[i].innerText();
      if (content) humanMessages.push({ content, index: i });
    } catch {
      try {
        const text = await userEls[i].innerText();
        if (text) humanMessages.push({ content: text, index: i });
      } catch {}
    }
  }

  // Click all Copy buttons to capture Claude responses via clipboard interception
  const copySel = [
    SELECTORS.copyButton,
    'button[aria-label*="Copy"]',
    'button[aria-label*="copy"]',
    '[data-testid*="copy"]',
  ];
  let copyButtons = [];
  for (const s of copySel) {
    copyButtons = await page.$$(s);
    if (copyButtons.length > 0) break;
  }
  for (let i = 0; i < copyButtons.length; i++) {
    try {
      await copyButtons[i].scrollIntoViewIfNeeded();
      await copyButtons[i].click();
      await page.waitForTimeout(150);
    } catch {}
  }
  await page.waitForTimeout(2000);

  // Merge human + claude in order (alternating)
  const messages = [];
  const maxLen = Math.max(humanMessages.length, claudeResponses.length);
  for (let i = 0; i < maxLen; i++) {
    if (i < humanMessages.length) {
      messages.push({ role: 'user', text: humanMessages[i].content });
    }
    if (i < claudeResponses.length) {
      messages.push({ role: 'assistant', text: claudeResponses[i] });
    }
  }
  return messages;
}

// Injected script to get all chat links from the save project
const GET_PROJECT_CHAT_LINKS = (projectName) => {
  const links = [];
  const allLinks = document.querySelectorAll('a[href*="/chat/"]');
  allLinks.forEach((a) => {
    const href = a.getAttribute('href');
    const title = (a.textContent || '').trim();
    if (href && !links.some((l) => l.href === href)) {
      links.push({ href, title: title || 'Untitled' });
    }
  });
  return links;
};

// Convert markdown-like text to docx paragraphs
function markdownToDocxParagraphs(md) {
  const paras = [];
  const lines = (md || '').split(/\r?\n/);
  let inCodeBlock = false;
  let codeLines = [];

  const flushCodeBlock = () => {
    if (codeLines.length > 0) {
      paras.push(
        new Paragraph({
          children: [
            new TextRun({
              text: codeLines.join('\n'),
              font: 'Consolas',
              size: 20,
            }),
          ],
          spacing: { after: 200 },
        })
      );
      codeLines = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        flushCodeBlock();
      }
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }
    const trimmed = line.trim();
    if (!trimmed) {
      paras.push(new Paragraph({ text: '', spacing: { after: 100 } }));
      continue;
    }
    const isHeader = /^#{1,6}\s/.test(trimmed);
    paras.push(
      new Paragraph({
        children: [
          new TextRun({
            text: trimmed,
            bold: isHeader,
            size: isHeader ? 28 : 24,
          }),
        ],
        spacing: { after: 150 },
      })
    );
  }
  flushCodeBlock();
  return paras;
}

async function main() {
  const userDataDir = path.join(__dirname, '..', '.playwright-claude-auth');
  let browser;
  try {
    browser = await chromium.launch({
      headless: !HEADED,
      channel: 'chrome',
      args: ['--disable-blink-features=AutomationControlled'],
    });
  } catch {
    // Fallback: use Chromium bundled with Playwright, or Edge on Windows
    browser = await chromium.launch({
      headless: !HEADED,
      channel: 'msedge',
      args: ['--disable-blink-features=AutomationControlled'],
    });
  }

  const context = await browser.newContext({
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 900 },
  });

  const page = await context.newPage();

  try {
    console.log('Navigating to Claude.ai...');
    await page.goto(CLAUDE_URL, { waitUntil: 'networkidle', timeout: 60000 });

    console.log(`Log in if needed. Waiting ${LOGIN_WAIT_MS / 1000} seconds before opening save project...`);
    await page.waitForTimeout(LOGIN_WAIT_MS);

    console.log('Opening save project...');
    await page.goto(PROJECT_URL, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(3000);

    // Scroll sidebar to load lazy chat list
    const sidebar = await page.$('[class*="sidebar"], [class*="chat-list"], [role="navigation"], aside');
    if (sidebar) {
      for (let i = 0; i < 5; i++) {
        await sidebar.evaluate((el) => el.scrollBy(0, 500));
        await page.waitForTimeout(500);
      }
    }
    await page.waitForTimeout(1000);

    // Get all chat links on the project page
    let chatLinks = await page.evaluate(GET_PROJECT_CHAT_LINKS);

    if (chatLinks.length === 0) {
      console.log('No chat links found on project page. Trying fallback selectors...');
      chatLinks = await page.evaluate(() => {
        const links = [];
        document.querySelectorAll('a[href*="/chat/"]').forEach((a) => {
          const href = a.getAttribute('href');
          const title = (a.textContent || '').trim().split('\n')[0].trim() || 'Untitled';
          if (href && !links.some((l) => l.href === href)) {
            links.push({ href, title });
          }
        });
        return links;
      });
    }

    if (chatLinks.length === 0) {
      console.log('No chat links found. Exporting the currently open chat if any...');
      chatLinks = [{ href: page.url(), title: 'Current Chat' }];
    }

    console.log(`Found ${chatLinks.length} chat(s) to export.`);

    const allChats = [];

    for (let i = 0; i < chatLinks.length; i++) {
      const { href, title } = chatLinks[i];
      const fullUrl = href.startsWith('http') ? href : new URL(href, CLAUDE_URL).href;
      console.log(`[${i + 1}/${chatLinks.length}] ${title}`);

      try {
        await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: 30000 });

        let messages = await extractChatWithCopyButtons(page);
        if (messages.length === 0) {
          const fallback = await page.evaluate(EXTRACT_DOM_FALLBACK);
          messages = fallback;
        }

        if (messages.length > 0) {
          const mdParts = [`# ${title}\n`, `\`${fullUrl}\`\n`];
          messages.forEach((m) => {
            const label = m.role === 'user' ? '_Human:_' : '_Claude:_';
            mdParts.push(`\n${label}\n\n${m.text}\n\n---`);
          });
          allChats.push({
            title,
            url: fullUrl,
            markdown: mdParts.join('\n'),
            messages,
          });
        } else {
          allChats.push({ title, url: fullUrl, markdown: `# ${title}\n\n(No messages extracted)\n`, messages: [] });
        }
      } catch (err) {
        console.warn(`  Skip: ${err.message}`);
        allChats.push({
          title,
          url: fullUrl,
          markdown: `# ${title}\n\n(Error: ${err.message})\n`,
          messages: [],
        });
      }
    }

    const combinedMd = [
      `# Claude.ai - Save Project Export`,
      `Exported: ${new Date().toISOString()}`,
      `Total chats: ${allChats.length}`,
      '',
      '---',
      '',
      ...allChats.map((c) => c.markdown),
    ].join('\n');

    const mdPath = path.join(OUT_DIR, 'save_chats.md');
    fs.writeFileSync(mdPath, combinedMd, 'utf8');
    console.log(`\nWrote: ${mdPath}`);

    // Build docx from combined markdown
    const docxParas = markdownToDocxParagraphs(combinedMd);
    const doc = new Document({
      sections: [
        {
          properties: {},
          children: docxParas,
        },
      ],
    });

    const docxBuffer = await Packer.toBuffer(doc);
    const docxPath = path.join(OUT_DIR, 'save_chats.docx');
    fs.writeFileSync(docxPath, docxBuffer);
    console.log(`Wrote: ${docxPath}`);

    console.log('\nDone.');
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
