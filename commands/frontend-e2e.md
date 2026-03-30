# /frontend-e2e — Comprehensive Frontend E2E Live Test

Perform a thorough live E2E test of a frontend web application using browser-bridge
MCP tools. Tests every page, interactive element, form, navigation flow, responsive
breakpoint, and accessibility rule through real browser interaction.

**Architecture**: Detect -> Crawl -> Universal -> A11y -> Visual/UX -> Navigation -> Responsive -> Interactive -> Performance -> Report. $0 cost, fully local via browser-bridge.

**CRITICAL: Execute the full test silently. Only interact with the user in Step 0
(URL/env confirmation) and Step 0.5 (auth probe). Present the full report at the end.**

**IMPORTANT: Per-page error isolation is MANDATORY. Every page's test suite is wrapped
in error handling — if any test fails or errors, mark it FAIL and continue to the next
page/test. NEVER abort the full run because of a single page failure.**

## Input

`$ARGUMENTS` = URL [flags]

| Flag | Description | Default |
|------|-------------|---------|
| `--focus <path>` | Test only pages matching this path prefix | all pages |
| `--skip-a11y` | Skip accessibility checks (Tier 1.5) | enabled |
| `--skip-responsive` | Skip responsive/breakpoint tests (Tier 3) | enabled |
| `--max-pages <n>` | Override default page cap | 20 |
| `--deep` | Set page cap to 50 instead of 20 | off |
| `--auth-cookie <name=value>` | Inject a session cookie before crawl | none |
| `--skip-visual` | Skip visual/UX quality checks (Tier 1.7) | enabled |
| `--allow-submit` | Allow form submission (localhost/staging only) | off |

---

## Step 0: Detect Application — MANDATORY, SILENT

1. Parse `$ARGUMENTS` for URL and flags
2. If no URL: probe common dev server ports (3000, 3001, 4200, 5173, 5174, 8000, 8080) via `mcp__browser-bridge__browser_navigate` to `http://localhost:{port}` — use first that responds
3. If still no URL: STOP — "Provide a URL or start a local dev server"
4. Call `mcp__browser-bridge__browser_get_tabs` to verify browser-bridge connection. If fails: STOP — "Browser-bridge not connected. Check Chrome extension."
5. **Production safety gate**: If URL is NOT `localhost`, `127.0.0.1`, or does NOT contain `staging`/`dev`/`test` in hostname:
   - Present warning: "This appears to be a production URL. Interactive tests (Tier 4) will NOT submit forms. Use `--allow-submit` only for test/staging environments."
   - Set internal flag `SAFE_MODE = true` (no form submissions, no button clicks that trigger navigation away)
6. Navigate to URL via `mcp__browser-bridge__browser_navigate`
7. Wait for page: try `mcp__browser-bridge__browser_wait_for_element` targeting `body` (timeout 15s). **Known issue**: `wait_for_element` may return "restricted URL" on localhost — if so, fall back to `browser_evaluate` with `!!document.body` check + 2s delay as workaround.
8. Take baseline screenshot via `mcp__browser-bridge__browser_screenshot`

**Framework detection** via `mcp__browser-bridge__browser_evaluate`:
```js
({
  react: !!document.querySelector('[data-reactroot], #root, #__next'),
  vue: !!document.querySelector('#app[data-v-app], [data-vue-app]'),
  angular: !!document.querySelector('[ng-version]'),
  nextjs: !!document.getElementById('__NEXT_DATA__'),
  nuxt: !!document.getElementById('__NUXT__'),
  svelte: !!document.querySelector('[class^="svelte-"]'),
  isSPA: window.history.pushState.toString().includes('native code') === false
        || !!document.querySelector('a[routerlink], a[data-navlink]')
        || window.location.hash.startsWith('#/'),
})
```

---

## Step 0.5: Auth Probe — MANDATORY

1. Check if current URL contains `/login`, `/signin`, `/auth`, or page has `input[type="password"]` in a `<form>`
2. If auth wall AND no `--auth-cookie`: STOP — "Auth wall detected at {url}. Re-run with `--auth-cookie session=<value>` or log in manually in the browser tab first."
3. If `--auth-cookie` provided: inject via `mcp__browser-bridge__browser_evaluate` — `document.cookie = '{name}={value}; path=/';` then reload

---

## Step 0.7: Dismiss Blockers — HELPER (called per navigation)

**This is a reusable helper called EVERY TIME a new page is navigated to, not just once at start.**

1. **Cookie consent**: `mcp__browser-bridge__browser_evaluate` — find `[id*="cookie"], [class*="consent"], [class*="cookie-banner"], [id*="gdpr"]` — click first accept/dismiss button
2. **Popups**: find `[class*="popup"] button[class*="close"], [class*="overlay"] button[class*="close"], [aria-label="Close"]` that are visible — click if found
3. Wait 500ms for transitions

---

## Step 1: Build Page Inventory — SILENT

1. **Collect links**: `mcp__browser-bridge__browser_evaluate` — gather all `<a>` with same-origin `href`, resolving relative URLs against `document.baseURI` (handles `<base href>` tag), deduplicating by pathname
2. **Normalize URLs**: strip trailing slashes, normalize protocol (handle HTTP->HTTPS redirects), lowercase hostnames
3. **Crawl depth 2**: navigate to each discovered link, collect its links, add to inventory. Call Step 0.7 dismiss helper on each navigation.
4. **Cap**: Stop at `--max-pages` (default 20, or 50 with `--deep`)
5. **Track visited**: Set of normalized URLs to prevent cycles
6. **Apply --focus**: if set, keep only pages matching prefix
7. **Rate limit**: 300ms delay between navigations
8. **Redirect detection**: after navigation, compare final URL to intended URL — if different, log redirect and use final URL in inventory

Output: ordered list of `{ url, title, depth }`.

**SPA without URL routing**: If the app is a React/Vue SPA with no route changes (URL stays at `/`), adapt: treat each navigable view (categories, tabs, modals) as a "page" by discovering clickable navigation buttons. Use `browser_evaluate` to find view-switching buttons, click each to enter the view, run per-page tests, then navigate back. Track views by button text/label instead of URL.

---

## Step 2: Tier 1 — Universal Assertions (per page)

For EACH page in inventory. **Per-page error isolation**: each page's tests wrapped in try/catch — on error, mark FAIL and continue.

On each page navigation:
1. Call Step 0.7 dismiss helper
2. **Wait for content stabilization** (max 8s timeout) via `mcp__browser-bridge__browser_evaluate`:
   ```js
   // Wait for animations to settle (max 3s)
   await Promise.race([
     new Promise(r => {
       const check = () => document.getAnimations().filter(a => a.playState === 'running').length === 0
         ? r() : setTimeout(check, 200);
       check();
     }),
     new Promise(r => setTimeout(r, 3000))
   ]);
   // Wait for skeleton screens to resolve (max 5s)
   await Promise.race([
     new Promise(r => {
       if (!document.querySelector('[class*="skeleton"], [class*="shimmer"], [aria-busy="true"]')) return r();
       const obs = new MutationObserver(() => {
         if (!document.querySelector('[class*="skeleton"], [class*="shimmer"], [aria-busy="true"]')) { obs.disconnect(); r(); }
       });
       obs.observe(document.body, { subtree: true, childList: true, attributes: true });
     }),
     new Promise(r => setTimeout(r, 5000))
   ]);
   ```

| # | Test | Tool | Pass Criteria |
|---|------|------|---------------|
| 1 | Page loads | `browser_navigate` + `browser_wait_for_element("body", timeout=15000)` | body present within 15s |
| 2 | No JS errors | `browser_console_messages(level="error")` | 0 errors (filter: ignore `favicon.ico` 404, React devtools, browser extension noise) |
| 3 | No broken images | `browser_evaluate` — `[...document.querySelectorAll('img[src]')].filter(i => !i.complete \|\| i.naturalWidth === 0)` | 0 broken |
| 4 | Page title | `browser_evaluate` — `document.title` | Non-empty |
| 5 | Viewport meta | `browser_evaluate` — `!!document.querySelector('meta[name="viewport"]')` | Present |
| 6 | No overflow | `browser_evaluate` — `document.documentElement.scrollWidth <= document.documentElement.clientWidth` | No horizontal overflow |
| 7 | Load time | `browser_evaluate` — Performance API `loadEventEnd - navigationStart` | Measured; WARN if >3000ms |

Screenshot: **every page** in inventory saved to `.workflow/screenshots/`:
- Landing page: `.workflow/screenshots/home.png`
- Subpages: `.workflow/screenshots/{slug}.png` (derive slug from URL path or page title)
- Full-page where possible: use `browser_screenshot` with `fullPage: true` and `savePath`
- On failure: also save `.workflow/screenshots/fail-{slug}-{test}.png`
- Create `.workflow/screenshots/` directory via Bash `mkdir -p` at start of Step 2

---

## Step 3: Tier 1.5 — Accessibility Checks (per page, skip if `--skip-a11y`)

All via single `mcp__browser-bridge__browser_evaluate` call — NO external libraries:

```js
({
  missingAlt: [...document.querySelectorAll('img:not([alt]):not([role="presentation"])')].map(e => e.src?.slice(0,80)),
  unlabeledInputs: [...document.querySelectorAll('input:not([type="hidden"]), select, textarea')]
    .filter(el => !el.labels?.length && !el.getAttribute('aria-label')
                && !el.getAttribute('aria-labelledby') && !el.title)
    .map(el => ({ tag: el.tagName, type: el.type, name: el.name, id: el.id })),
  missingLang: !document.documentElement.lang,
  missingSkipLink: !document.querySelector('a[href="#main"], a[href="#content"], [class*="skip"]'),
  headingGaps: [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
    .map(h => parseInt(h.tagName[1]))
    .reduce((a, l, i, arr) => { if (i > 0 && l - arr[i-1] > 1) a.push(`h${arr[i-1]}->h${l}`); return a; }, []),
  emptyButtons: [...document.querySelectorAll('button, a[href], [role="button"]')]
    .filter(el => !el.textContent?.trim() && !el.getAttribute('aria-label')
                && !el.getAttribute('aria-labelledby') && !el.title && !el.querySelector('img[alt]'))
    .map(el => el.outerHTML.slice(0,100)),
  positiveTabindex: [...document.querySelectorAll('[tabindex]')]
    .filter(el => parseInt(el.getAttribute('tabindex')) > 0).length,
  badAriaButtons: [...document.querySelectorAll('[role="button"]')]
    .filter(el => !['BUTTON','A','INPUT'].includes(el.tagName) && el.getAttribute('tabindex') === null)
    .map(el => el.outerHTML.slice(0,80)),
})
```

Severity: CRITICAL = `missingLang`, `unlabeledInputs`, `emptyButtons`. HIGH = `missingAlt`, `headingGaps`, `badAriaButtons`. MEDIUM = `missingSkipLink`, `positiveTabindex`.

---

## Step 3.5: Tier 1.7 — Visual & UX Quality (per page, skip if `--skip-visual`)

All checks via `mcp__browser-bridge__browser_evaluate` — no external libraries. Runs per page
(same as T1/T1.5). **Batch all `getComputedStyle` reads — no DOM writes between reads** to
avoid layout thrashing. Target: < 5s per page.

### 2A: Color Contrast Check

Single `browser_evaluate` call sampling the **20 largest text elements**. Walks ancestors for
effective background color, handles transparent backgrounds, flags gradient/image as untestable.

```js
(() => {
  function luminance(r, g, b) {
    const [rs, gs, bs] = [r, g, b].map(c => {
      c = c / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
  }
  function contrastRatio(l1, l2) {
    const lighter = Math.max(l1, l2), darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }
  function parseRgba(str) {
    const m = str.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    return m ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] !== undefined ? +m[4] : 1 } : null;
  }
  function getEffectiveBg(el) {
    let node = el;
    while (node && node !== document) {
      const s = getComputedStyle(node);
      if (s.backgroundImage !== 'none') return { untestable: true, reason: 'background-image' };
      const rgba = parseRgba(s.backgroundColor);
      if (rgba && rgba.a > 0.05) {
        if (rgba.a < 1) {
          return { r: Math.round(rgba.a * rgba.r + (1 - rgba.a) * 255),
                   g: Math.round(rgba.a * rgba.g + (1 - rgba.a) * 255),
                   b: Math.round(rgba.a * rgba.b + (1 - rgba.a) * 255) };
        }
        return { r: rgba.r, g: rgba.g, b: rgba.b };
      }
      node = node.parentElement;
    }
    return { r: 255, g: 255, b: 255 };
  }

  const textEls = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,span,a,button,label,li,td,th')]
    .filter(el => el.offsetParent !== null && el.textContent.trim().length > 0)
    .sort((a, b) => parseFloat(getComputedStyle(b).fontSize) - parseFloat(getComputedStyle(a).fontSize))
    .slice(0, 20);

  const failures = [], skipped = [];
  for (const el of textEls) {
    const style = getComputedStyle(el);
    const fg = parseRgba(style.color);
    if (!fg) continue;
    const bg = getEffectiveBg(el);
    if (bg.untestable) { skipped.push({ text: el.textContent.trim().slice(0,30), reason: bg.reason }); continue; }
    const fgL = luminance(fg.r, fg.g, fg.b);
    const bgL = luminance(bg.r, bg.g, bg.b);
    const ratio = contrastRatio(fgL, bgL);
    const fontSize = parseFloat(style.fontSize);
    const isBold = parseInt(style.fontWeight) >= 700;
    const isLargeText = fontSize >= 24 || (fontSize >= 18.66 && isBold);
    const threshold = isLargeText ? 3 : 4.5;
    if (ratio < threshold) {
      failures.push({
        text: el.textContent.trim().slice(0, 30), tag: el.tagName,
        ratio: Math.round(ratio * 100) / 100, needed: threshold,
        fontSize: Math.round(fontSize), fg: style.color, bg: `rgb(${bg.r},${bg.g},${bg.b})`
      });
    }
  }
  return { contrastFailures: failures, skipped, sampled: textEls.length };
})()
```

Severity: FAIL if any ratio below WCAG AA. WARN if within 0.5 of threshold. SKIP for gradient/image backgrounds.

### 2B: Typography & Readability

```js
(() => {
  const body = getComputedStyle(document.body);
  const bodyFontSize = parseFloat(body.fontSize);
  const paragraphs = [...document.querySelectorAll('p')]
    .filter(el => el.offsetParent !== null && el.textContent.trim().length > 50);

  const issues = [];

  if (bodyFontSize < 14) issues.push({ check: 'bodyFontSize', value: bodyFontSize, threshold: 14, severity: 'FAIL' });

  for (const p of paragraphs.slice(0, 10)) {
    const s = getComputedStyle(p);
    const lineHeight = parseFloat(s.lineHeight) / parseFloat(s.fontSize);
    const width = p.getBoundingClientRect().width;
    const charsPerLine = width / (parseFloat(s.fontSize) * 0.5);

    if (lineHeight < 1.4 && !isNaN(lineHeight))
      issues.push({ check: 'lineHeight', el: p.textContent.slice(0,30), value: Math.round(lineHeight*100)/100, threshold: 1.4, severity: 'WARN' });
    if (charsPerLine > 80)
      issues.push({ check: 'lineWidth', el: p.textContent.slice(0,30), value: Math.round(charsPerLine), threshold: 80, severity: 'WARN' });
  }

  const GENERIC = new Set(['sans-serif','serif','monospace','cursive','fantasy','system-ui','-apple-system','BlinkMacSystemFont','Segoe UI','ui-sans-serif','ui-serif','ui-monospace']);
  const fonts = new Set([...document.querySelectorAll('*')]
    .filter(el => el.offsetParent !== null)
    .slice(0, 50)
    .map(el => {
      const first = getComputedStyle(el).fontFamily.split(',')[0].trim().replace(/['"]/g, '');
      return GENERIC.has(first) ? null : first;
    })
    .filter(Boolean));

  if (fonts.size > 4) issues.push({ check: 'fontCount', value: fonts.size, threshold: 4, severity: 'WARN', fonts: [...fonts] });

  return { bodyFontSize, fontFamilies: [...fonts], readabilityIssues: issues };
})()
```

### 2C: Touch Target & Click Target Sizing

Tiered thresholds using `getBoundingClientRect` (handles CSS transforms). Skips inline `<a>` in
running text per WCAG 2.5.8 exception.

```js
(() => {
  const interactives = [...document.querySelectorAll(
    'button, a[href], input, select, textarea, [role="button"], [role="link"], [role="tab"], [onclick]'
  )].filter(el => {
    if (el.offsetParent === null) return false;
    if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') return false;
    return true;
  });

  const fails = [], warns = [];
  for (const el of interactives.slice(0, 50)) {
    const rect = el.getBoundingClientRect();
    const w = Math.round(rect.width), h = Math.round(rect.height);
    const text = (el.textContent?.trim() || el.getAttribute('aria-label') || '').slice(0, 30);
    if (w < 24 || h < 24) {
      fails.push({ tag: el.tagName, text, width: w, height: h, level: 'FAIL (<24px WCAG AA)' });
    } else if (w < 44 || h < 44) {
      warns.push({ tag: el.tagName, text, width: w, height: h, level: 'WARN (24-43px, below AAA)' });
    }
  }
  return { totalInteractive: interactives.length, fails, warns, failCount: fails.length, warnCount: warns.length };
})()
```

| Size | Level | Action |
|------|-------|--------|
| < 24px | FAIL | WCAG 2.2 AA minimum violated |
| 24-43px | WARN | Below AAA / Material Design / Apple HIG |
| >= 44px | PASS | Meets all standards |

### 2D: Focus Visibility

Synthetic Tab keydown does NOT trigger `:focus-visible` in Chrome/CDP. **Stylesheet scan is PRIMARY**
signal (done in 2F). `el.focus()` style comparison is SECONDARY — only reliable for `input`,
`textarea`, `select` which receive `:focus-visible` from script focus.

```js
(() => {
  const keyboardOperable = [...document.querySelectorAll(
    'input:not([type="hidden"]), textarea, select'
  )].filter(el => el.offsetParent !== null).slice(0, 10);

  const results = [];
  for (const el of keyboardOperable) {
    const s1 = getComputedStyle(el);
    const before = { outline: s1.outline, boxShadow: s1.boxShadow, border: s1.border, bg: s1.backgroundColor };
    el.focus();
    const s2 = getComputedStyle(el);
    const after = { outline: s2.outline, boxShadow: s2.boxShadow, border: s2.border, bg: s2.backgroundColor };
    const hasVisibleFocus = after.outline !== before.outline
      || after.boxShadow !== before.boxShadow
      || after.border !== before.border
      || after.bg !== before.bg;
    results.push({
      tag: el.tagName, type: el.type,
      text: (el.getAttribute('aria-label') || el.name || '').slice(0, 20),
      hasVisibleFocus
    });
    el.blur();
  }

  const noFocus = results.filter(r => !r.hasVisibleFocus);
  return { tested: results.length, noFocusIndicator: noFocus,
           note: 'Stylesheet :focus-visible scan is primary signal (from 2F). Style comparison only reliable for input/textarea/select.' };
})()
```

**Severity logic** (combines stylesheet scan from 2F + style test):
- Site has `:focus-visible` CSS rules -> PASS
- No `:focus-visible` rules AND >80% of inputs lack visible focus -> FAIL
- No `:focus-visible` rules AND some inputs lack focus -> WARN
- Always note: "Manual Tab-key verification recommended for buttons/links"

### 2E: Visual Consistency & Layout Quality

Improved clipping detection (full matrix with +4px buffer, skip scroll/auto containers).
Detects text-overflow/ellipsis and line-clamp.

```js
(() => {
  const highZIndex = [...document.querySelectorAll('*')]
    .filter(el => el.offsetParent !== null)
    .map(el => ({ el, z: parseInt(getComputedStyle(el).zIndex) }))
    .filter(({ z }) => !isNaN(z) && z > 9999)
    .map(({ el, z }) => ({ tag: el.tagName, class: el.className?.toString().slice(0,40), zIndex: z }))
    .slice(0, 5);

  function isClippingText(el) {
    const s = getComputedStyle(el);
    if (!el.textContent?.trim() || !['block','flex','grid','list-item','-webkit-box'].includes(s.display)) return null;
    if (s.overflowY === 'scroll' || s.overflowY === 'auto' || s.overflowX === 'scroll' || s.overflowX === 'auto') return null;
    if (s.overflowY === 'hidden' && el.scrollHeight > Math.ceil(el.clientHeight) + 4) return 'overflow-hidden-y';
    if (s.overflowX === 'hidden' && el.scrollWidth > Math.ceil(el.clientWidth) + 4) return 'overflow-hidden-x';
    if (s.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth) return 'text-overflow-ellipsis';
    if (s.webkitLineClamp !== 'none' && s.webkitLineClamp && el.scrollHeight > Math.ceil(el.clientHeight) + 4) return 'line-clamp';
    if (s.whiteSpace === 'nowrap' && el.scrollWidth > Math.ceil(el.clientWidth) + 4) return 'nowrap-overflow';
    return null;
  }

  const clippedText = [...document.querySelectorAll('p,div,span,h1,h2,h3,h4,h5,h6,li,td,th,label')]
    .filter(el => el.offsetParent !== null)
    .map(el => ({ el, clip: isClippingText(el) }))
    .filter(({ clip }) => clip !== null)
    .map(({ el, clip }) => ({
      tag: el.tagName, text: el.textContent.trim().slice(0, 40),
      clipType: clip, visibleH: el.clientHeight, actualH: el.scrollHeight
    }))
    .slice(0, 15);

  const sampleEls = [...document.querySelectorAll('*')].filter(el => el.offsetParent !== null).slice(0, 200);
  const styles = sampleEls.map(el => getComputedStyle(el));
  const layoutMethod = {
    flexContainers: styles.filter(s => s.display === 'flex' || s.display === 'inline-flex').length,
    gridContainers: styles.filter(s => s.display === 'grid' || s.display === 'inline-grid').length,
  };

  return { highZIndex, clippedText, layoutMethod };
})()
```

### 2F: Platform & Preference Checks (unified stylesheet scan)

Single CSSOM walk with unified try/catch. Scans for `:focus-visible`, `prefers-color-scheme: dark`,
and `prefers-reduced-motion` in one pass.

```js
(() => {
  let hasDarkMode = false, hasReducedMotion = false, hasFocusVisible = false;
  const colorScheme = getComputedStyle(document.documentElement).colorScheme;
  if (colorScheme && colorScheme !== 'normal') hasDarkMode = true;

  try {
    for (const sheet of document.styleSheets) {
      try {
        for (const rule of sheet.cssRules) {
          const text = rule.cssText || '';
          if (rule.conditionText) {
            if (rule.conditionText.includes('prefers-color-scheme: dark')) hasDarkMode = true;
            if (rule.conditionText.includes('prefers-reduced-motion')) hasReducedMotion = true;
          }
          if (text.includes(':focus-visible')) hasFocusVisible = true;
        }
      } catch(e) {}
    }
  } catch(e) {}
  const osWantsReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const vhElements = [...document.querySelectorAll('*')]
    .filter(el => el.offsetParent !== null && getComputedStyle(el).height === '100vh')
    .map(el => ({ tag: el.tagName, class: el.className?.toString().slice(0,40) }))
    .slice(0, 5);

  const viewportMeta = document.querySelector('meta[name="viewport"]');
  const blocksPinchZoom = viewportMeta?.content?.includes('user-scalable=no')
    || viewportMeta?.content?.includes('maximum-scale=1');

  const hasPrintStylesheet = [...document.styleSheets].some(s => {
    try { return s.media.mediaText.includes('print'); } catch(e) { return false; }
  });

  return {
    cssFeatures: { focusVisible: hasFocusVisible, darkMode: hasDarkMode, reducedMotion: hasReducedMotion },
    darkMode: { supported: hasDarkMode, colorScheme },
    reducedMotion: { supported: hasReducedMotion, osPreference: osWantsReducedMotion,
                     issue: osWantsReducedMotion && !hasReducedMotion },
    mobileVhTrap: { count: vhElements.length, elements: vhElements },
    pinchZoom: { blocked: !!blocksPinchZoom, viewport: viewportMeta?.content?.slice(0,100) },
    printStylesheet: hasPrintStylesheet
  };
})()
```

| Check | FAIL | WARN |
|-------|------|------|
| Dark mode | - | Not supported (informational) |
| Reduced motion | OS wants it but site ignores it | No rules found |
| 100vh trap | - | Any element uses 100vh (mobile risk) |
| Pinch-zoom | `user-scalable=no` (WCAG 1.4.4 violation) | `maximum-scale=1` |
| Print stylesheet | - | Missing (for content-heavy pages) |

### Tier 1.7 Severity Summary

| Check | FAIL | WARN |
|-------|------|------|
| Contrast ratio | Below WCAG AA threshold | Within 0.5 / bg-image SKIP |
| Body font size | < 14px | 14-15px |
| Line height | - | < 1.4 |
| Line width | - | > 80 chars/line |
| Font count | - | > 4 families |
| Touch targets | Any < 24px (WCAG AA) | 24-43px (below AAA) |
| Focus visibility | >80% no focus + no :focus-visible rules | >60% or any lacking |
| Clipped text | - | Any detected (5 types) |
| Z-index | - | Any > 9999 |
| Pinch-zoom blocked | user-scalable=no | maximum-scale=1 |
| Reduced motion | OS wants + site ignores | No rules found |
| Dark mode | - | Not supported (info) |
| 100vh trap | - | Any element (mobile risk) |

---

## Step 4: Tier 2 — Navigation & Routing

1. **Deep linking**: Pick 10 random pages from inventory -> navigate directly by URL -> verify page loads (not 404, not redirect to home)
2. **Back/forward**: Navigate page A -> page B -> `mcp__browser-bridge__browser_navigate` with url="back" -> verify URL = page A
3. **404 page**: Navigate to `{origin}/definitely-not-a-page-12345` -> check for 404 indicator (status text, "not found" content, or redirect to home)
4. **Hash links**: On landing page, find `a[href^="#"]` -> click each -> verify scroll position changed (`window.scrollY`)
5. **SPA reload persistence**: If SPA detected, navigate to page B -> reload -> verify page B content still renders

---

## Step 5: Tier 3 — Responsive Testing (skip if `--skip-responsive`)

Test **landing page + up to 5 most-linked pages** only (not all).

3 breakpoints — NOTE: browser-bridge has no native viewport resize. Strategy:
1. Use `mcp__browser-bridge__browser_evaluate` to check `window.matchMedia('(max-width: 768px)').matches` to see what current viewport triggers
2. If `browser_screenshot` with `savePath` is available, take screenshots at current viewport
3. Check for responsive indicators:
   - Horizontal overflow: `document.documentElement.scrollWidth > document.documentElement.clientWidth`
   - Hamburger detection: `[class*="hamburger"], [class*="menu-toggle"], [aria-label*="menu"], button[class*="nav"]`
   - If hamburger visible: click -> verify menu opens (new elements visible), press Escape -> verify closes
4. Screenshot per page (save as `responsive-{page-slug}.png`)

**Known limitation**: True CSS media query testing requires actual viewport resize which browser-bridge may not support. Document this in the report and recommend manual verification at mobile breakpoints.

---

## Step 6: Tier 4 — Interactive Element Testing (per page)

**State handling**: Navigate to each page fresh (don't clear localStorage — it may contain auth tokens).

**Element discovery** via single `mcp__browser-bridge__browser_evaluate`:
```js
({
  buttons: [...document.querySelectorAll(
    'button:not([disabled]), [role="button"]:not([aria-disabled="true"]), input[type="submit"], input[type="button"]'
  )].filter(el => el.offsetParent !== null)
    .map((el,i) => ({ i, text: (el.textContent?.trim()||el.getAttribute('aria-label')||'').slice(0,50), tag: el.tagName })),
  forms: [...document.querySelectorAll('form, [role="form"]')]
    .map((f,i) => ({ i, action: f.action, method: f.method, fields: f.querySelectorAll('input:not([type="hidden"]), select, textarea').length })),
  modals: [...document.querySelectorAll('[aria-haspopup="dialog"], [data-modal], [data-toggle="modal"], [data-bs-toggle="modal"]')]
    .filter(el => el.offsetParent !== null)
    .map((el,i) => ({ i, text: el.textContent?.trim().slice(0,50) })),
  tabs: [...document.querySelectorAll('[role="tab"]')]
    .map((el,i) => ({ i, text: el.textContent?.trim().slice(0,50), selected: el.getAttribute('aria-selected') })),
  accordions: [...document.querySelectorAll('details > summary, [role="button"][aria-expanded]')]
    .map((el,i) => ({ i, text: el.textContent?.trim().slice(0,50), expanded: el.getAttribute('aria-expanded')||String(el.parentElement?.open) })),
  selects: [...document.querySelectorAll('select')]
    .map((el,i) => ({ i, name: el.name, options: el.options.length })),
})
```

**Button testing** (cap: first 20 buttons per page):
1. Record page URL and DOM content hash before click
2. Click via `mcp__browser-bridge__browser_execute` (action: "click")
3. Wait 500ms
4. Check: did URL change? New console error? Modal appear?
5. If URL changed: navigate back. If modal appeared: press Escape to dismiss.
6. Screenshot on failure only

**Form testing**:
- **Always**: Fill fields with type-appropriate test data via `mcp__browser-bridge__browser_fill_form` / `mcp__browser-bridge__browser_insert_text`:
  - `email` -> `test@example.com`, `text` -> `Test Input`, `tel` -> `555-0100`
  - `number` -> `42`, `password` -> `TestPass123!`, `url` -> `https://example.com`
  - `select` -> 2nd option, `textarea` -> `Test content for textarea field.`
- **Always**: Test validation — clear required fields, trigger submit via `mcp__browser-bridge__browser_press_key("Enter")` on form, verify error indicators appear: `[aria-invalid="true"]`, `[role="alert"]`, `.error`, elements with `[aria-live]`
- **Only if `--allow-submit` AND (localhost or staging URL)**: Actually submit the form and verify response
- **Production (default)**: Fill and validate only — do NOT submit. Note in report: "Form validation tested; submission skipped (production safety mode)"

**Modal testing** (for each discovered modal trigger):
1. Click trigger -> wait for `[role="dialog"], dialog, [aria-modal="true"]` (timeout 3s)
2. If appears: verify visible, press Escape -> verify dismissed
3. Re-open -> find close button inside dialog -> click -> verify dismissed
4. Screenshot if modal fails to open/close

**Tab testing**: Click each tab -> verify `aria-selected="true"` on clicked, associated `[role="tabpanel"]` visible, other tabs deselected

**Accordion testing**: Click to expand -> verify `aria-expanded="true"` or `<details open>` -> click to collapse -> verify

**Edge case inventory** (detect and report only — no deep testing):
- `iframe` -> count, note cross-origin vs same-origin
- `canvas, [class*="chart"]` -> flag, take screenshot
- `[contenteditable="true"]` -> flag as rich text editor
- `input[type="file"]` -> verify labeled, note accept attribute
- `[draggable="true"]` -> flag

---

## Step 7: Tier 5 — Performance Spot Checks (landing page only)

1. Navigate away then back for cold load measurement
2. `mcp__browser-bridge__browser_evaluate`:
   ```js
   ({
     loadTime: performance.timing.loadEventEnd - performance.timing.navigationStart,
     lcp: performance.getEntriesByType('largest-contentful-paint').pop()?.startTime || null,
     cls: performance.getEntriesByType('layout-shift').reduce((s, e) => s + (e.hadRecentInput ? 0 : e.value), 0),
   })
   ```
3. Lazy loading: `mcp__browser-bridge__browser_scroll` down 5 times -> verify no remaining `[class*="skeleton"], [aria-busy="true"]`

Thresholds: WARN if load >3000ms, LCP >2500ms, CLS >0.1

---

## Step 8: Generate Report

Create `.workflow/` directory if needed (via Bash `mkdir -p`). Save to `.workflow/frontend-e2e-report.md`.

```markdown
# Frontend E2E Test Report

**URL**: {url}
**Framework**: {detected}
**Navigation**: {SPA|MPA}
**Pages tested**: {n}/{total discovered}
**Timestamp**: {ISO 8601}
**Duration**: ~{minutes}
**Mode**: {production safety | full (--allow-submit)}
**Flags**: {flags}

## Summary

| Tier | Tests | PASS | FAIL | WARN | SKIP |
|------|-------|------|------|------|------|
| T1: Universal | | | | | |
| T1.5: Accessibility | | | | | |
| T1.7: Visual & UX | | | | | |
| T2: Navigation | | | | | |
| T3: Responsive | | | | | |
| T4: Interactive | | | | | |
| T5: Performance | | | | | |
| **TOTAL** | | | | | |

## Visual Snapshot Gallery
Screenshots saved to `.workflow/screenshots/`:
| Page | Path | Visual Issues |
|------|------|---------------|
| Home | `screenshots/home.png` | {count} |
| {page} | `screenshots/{slug}.png` | {count} |
| ... | ... | ... |

## Visual UX Summary
| Check | Status | Details |
|-------|--------|---------|
| Color Contrast (WCAG AA) | {PASS/FAIL/SKIP} | {n} failures, {n} skipped (bg-image) |
| Typography Readability | {PASS/WARN} | Body: {size}px, {n} line-height issues |
| Touch Targets (24px AA / 44px AAA) | {PASS/WARN/FAIL} | {n} FAIL (<24px), {n} WARN (24-43px) |
| Focus Visibility | {PASS/WARN/FAIL} | {n}/{total} lack focus; :focus-visible={yes/no} |
| Text Clipping | {PASS/WARN} | {n} clipped ({types}) |
| Font Count | {PASS/WARN} | {n} families: {list} |
| Dark Mode | {supported/not} | {color-scheme value} |
| Reduced Motion | {PASS/WARN/FAIL} | OS={on/off}, site rules={yes/no} |
| Pinch Zoom | {PASS/FAIL} | {viewport meta content} |
| 100vh Trap | {PASS/WARN} | {n} elements |

## Quick Wins
{Top 5 easiest visual fixes with highest impact — auto-generated from Tier 1.7 findings.
Prioritize: contrast fixes, touch target sizing, missing focus styles, font consolidation.}

## CRITICAL Failures
{grouped by page, evidence snippets, screenshot refs}

## HIGH Failures
{grouped by page}

## MEDIUM Issues
{one-line per finding}

## LOW / Informational
{one-line per finding}

## Edge Cases Detected
{iframes, canvas, rich text editors, file inputs, drag-and-drop — flagged}

## Intercepted/Skipped Actions
{forms not submitted in production mode, buttons skipped, etc.}

## Performance Summary (landing page)
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Load Time | {ms} | 3000ms | |
| LCP | {ms} | 2500ms | |
| CLS | {score} | 0.1 | |

## Known Limitations
- Responsive tests: viewport resize limited to what browser-bridge supports
- Form submission: skipped in production safety mode
- Shadow DOM: not traversed (document limitation)
- Cross-origin iframes: cannot be tested
```

---

## Error Handling

| Error | Action |
|-------|--------|
| App not reachable | STOP: "Cannot reach {url}. Is the dev server running?" |
| Browser-bridge not connected | STOP: "Browser-bridge not connected. Check Chrome extension." |
| Auth wall detected | STOP: "Auth wall at {url}. Use `--auth-cookie` or log in manually." |
| Page timeout (>15s) | Mark FAIL, continue to next page |
| Click triggers JS alert | Report WARNING, instruct user to dismiss |
| Too many pages (>{cap}) | Cap and report "Tested {cap}/{total}. Use --deep or --focus." |
| Element not found for test | Mark SKIP, continue |
| Bot detection / CAPTCHA | STOP Tier 4 for that page, report: "Bot detection triggered" |
| browser-bridge disconnects mid-run | Save partial report, STOP: "Browser connection lost at page {n}/{total}" |
