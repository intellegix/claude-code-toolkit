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
| `--skip-design` | Skip visual design quality checks (Tier 1.8) | enabled |
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

See also: Tier 1.8 Visual Design Quality checks below for spacing, rhythm, elevation, and cognitive load analysis.

---

## Step 3.7: Tier 1.8 — Visual Design Quality (per page, skip if `--skip-design`)

All checks via `mcp__browser-bridge__browser_evaluate` — no external libraries. Runs per page.
Target: < 2s per page for all 10 checks combined. Returns a composite **Visual Design Quality
Score (VDQS, 0-100)** grading overall design system discipline.

VDQS Grades: A (90-100) = tight design system | B (75-89) = minor inconsistencies |
C (60-74) = moderate drift | D (40-59) = significant design debt | F (<40) = no discernible system

### 3.7.1 Spacing Entropy Score (15pts)

TreeWalker (cap 400 els) + getComputedStyle on margin/padding/gap. Count unique spacing values.
Check grid adherence (4px/8px multiples). PASS ≤8 unique, WARN 9-12, FAIL >12. Demote if grid
adherence <60%.

```js
(() => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, {
    acceptNode: n => n.offsetParent !== null || n === document.body ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP
  });
  const spacingValues = new Map();
  const props = ['marginTop','marginRight','marginBottom','marginLeft','paddingTop','paddingRight','paddingBottom','paddingLeft','gap','rowGap','columnGap'];
  let count = 0;
  while (walker.nextNode() && count < 400) {
    const s = getComputedStyle(walker.currentNode);
    for (const p of props) {
      const v = parseFloat(s[p]);
      if (v > 0 && v < 200) {
        const rounded = Math.round(v);
        spacingValues.set(rounded, (spacingValues.get(rounded) || 0) + 1);
      }
    }
    count++;
  }
  const unique = [...spacingValues.keys()].sort((a, b) => a - b);
  const onGrid = unique.filter(v => v % 4 === 0).length;
  const gridAdherence = unique.length > 0 ? Math.round((onGrid / unique.length) * 100) : 100;
  let status = unique.length <= 8 ? 'PASS' : unique.length <= 12 ? 'WARN' : 'FAIL';
  if (status === 'PASS' && gridAdherence < 60) status = 'WARN';
  return {
    check: '3.7.1-spacing-entropy', status, weight: 15,
    uniqueCount: unique.length, uniqueValues: unique.slice(0, 20),
    gridAdherence, elementsScanned: count,
    topValues: [...spacingValues.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([v, c]) => ({ value: v, count: c }))
  };
})()
```

### 3.7.2 Visual Rhythm Index (12pts)

getBoundingClientRect on section/article/card blocks (cap 30). Compute inter-block gaps, calculate
CV (sigma/mu). PASS CV<0.2, WARN 0.2-0.5, FAIL >0.5. SKIP if <3 blocks.

```js
(() => {
  const blocks = [...document.querySelectorAll('section, article, [class*="card"], [class*="Card"], main > div > div')]
    .filter(el => el.offsetParent !== null && el.getBoundingClientRect().height > 40)
    .slice(0, 30);
  if (blocks.length < 3) return { check: '3.7.2-visual-rhythm', status: 'SKIP', weight: 12, reason: 'fewer than 3 content blocks found', blockCount: blocks.length };
  const rects = blocks.map(el => el.getBoundingClientRect());
  const gaps = [];
  for (let i = 1; i < rects.length; i++) {
    const gap = rects[i].top - rects[i - 1].bottom;
    if (gap >= 0 && gap < 500) gaps.push(Math.round(gap));
  }
  if (gaps.length < 2) return { check: '3.7.2-visual-rhythm', status: 'SKIP', weight: 12, reason: 'insufficient measurable gaps', gapCount: gaps.length };
  const mean = gaps.reduce((s, g) => s + g, 0) / gaps.length;
  const variance = gaps.reduce((s, g) => s + (g - mean) ** 2, 0) / gaps.length;
  const stddev = Math.sqrt(variance);
  const cv = mean > 0 ? Math.round((stddev / mean) * 100) / 100 : 0;
  const status = cv < 0.2 ? 'PASS' : cv <= 0.5 ? 'WARN' : 'FAIL';
  return {
    check: '3.7.2-visual-rhythm', status, weight: 12,
    cv, mean: Math.round(mean), stddev: Math.round(stddev),
    gapValues: gaps, blockCount: blocks.length
  };
})()
```

### 3.7.3 Elevation Layer Audit (8pts)

Walk box-shadow values (cap 500 els). Normalize shadows (round to 2px, normalize alpha to 1
decimal). Count unique. PASS ≤4, WARN 5, FAIL >5. Zero shadows = PASS (flat design valid).

```js
(() => {
  const els = [...document.querySelectorAll('*')].filter(el => el.offsetParent !== null).slice(0, 500);
  const shadowSet = new Set();
  for (const el of els) {
    const shadow = getComputedStyle(el).boxShadow;
    if (shadow && shadow !== 'none') {
      const normalized = shadow.replace(/[\d.]+px/g, m => {
        return Math.round(parseFloat(m) / 2) * 2 + 'px';
      }).replace(/[\d.]+\)/g, m => {
        return (Math.round(parseFloat(m) * 10) / 10) + ')';
      });
      shadowSet.add(normalized);
    }
  }
  const uniqueCount = shadowSet.size;
  let status;
  if (uniqueCount === 0) status = 'PASS';
  else if (uniqueCount <= 4) status = 'PASS';
  else if (uniqueCount === 5) status = 'WARN';
  else status = 'FAIL';
  return {
    check: '3.7.3-elevation-layers', status, weight: 8,
    uniqueShadows: uniqueCount,
    shadows: [...shadowSet].slice(0, 8).map(s => s.slice(0, 80)),
    note: uniqueCount === 0 ? 'flat design (no shadows) — valid' : null
  };
})()
```

### 3.7.4 Whitespace Breathing Room (10pts)

For card/panel/widget/tile/article elements (cap 20). Compute fillRatio = sum(childContentArea) /
parentBoundingArea. PASS if 35-92%, WARN outside. FAIL if >30% of cards are out of range.

```js
(() => {
  const containers = [...document.querySelectorAll('[class*="card"], [class*="Card"], [class*="panel"], [class*="Panel"], [class*="widget"], [class*="tile"], article')]
    .filter(el => el.offsetParent !== null && el.children.length > 0)
    .slice(0, 20);
  if (containers.length === 0) return { check: '3.7.4-whitespace-breathing', status: 'SKIP', weight: 10, reason: 'no card/panel/widget elements found' };
  const results = [];
  let outOfRange = 0;
  for (const container of containers) {
    const parentRect = container.getBoundingClientRect();
    const parentArea = parentRect.width * parentRect.height;
    if (parentArea < 100) continue;
    let childArea = 0;
    for (const child of container.children) {
      if (child.offsetParent === null) continue;
      const r = child.getBoundingClientRect();
      childArea += r.width * r.height;
    }
    const fillRatio = Math.round((childArea / parentArea) * 100);
    const ok = fillRatio >= 35 && fillRatio <= 92;
    if (!ok) outOfRange++;
    results.push({ tag: container.tagName, class: (container.className?.toString() || '').slice(0, 30), fillRatio, ok });
  }
  const total = results.length || 1;
  const outPct = Math.round((outOfRange / total) * 100);
  const status = outPct > 30 ? 'FAIL' : outOfRange > 0 ? 'WARN' : 'PASS';
  return {
    check: '3.7.4-whitespace-breathing', status, weight: 10,
    outOfRange, total: results.length, outPct,
    details: results.slice(0, 10)
  };
})()
```

### 3.7.5 Transition Vocabulary (8pts)

getComputedStyle on interactive elements (cap 200) for transitionTimingFunction +
transitionDuration. Normalize cubic-bezier to 2-decimal, bucket durations to 50ms.
PASS ≤3 unique easings, WARN 4-5, FAIL >5.

```js
(() => {
  const els = [...document.querySelectorAll('button, a[href], input, select, textarea, [role="button"], [role="tab"], [class*="btn"]')]
    .filter(el => el.offsetParent !== null).slice(0, 200);
  const easings = new Set();
  const durations = new Set();
  for (const el of els) {
    const s = getComputedStyle(el);
    const tf = s.transitionTimingFunction;
    const td = s.transitionDuration;
    if (td && td !== '0s') {
      const normalizedEasing = tf.replace(/(\d+\.\d{3,})/g, m => parseFloat(m).toFixed(2));
      easings.add(normalizedEasing);
      const ms = td.split(',').map(d => {
        const v = parseFloat(d);
        return d.includes('ms') ? Math.round(v / 50) * 50 : Math.round(v * 1000 / 50) * 50;
      });
      ms.forEach(m => durations.add(m));
    }
  }
  const uniqueEasings = easings.size;
  const status = uniqueEasings <= 3 ? 'PASS' : uniqueEasings <= 5 ? 'WARN' : 'FAIL';
  return {
    check: '3.7.5-transition-vocab', status, weight: 8,
    uniqueEasings, uniqueDurations: durations.size,
    easingList: [...easings].slice(0, 8),
    durationBuckets: [...durations].sort((a, b) => a - b),
    elementsScanned: els.length,
    note: easings.size === 0 ? 'no transitions found on interactive elements' : null
  };
})()
```

### 3.7.6 Border Radius Consistency (8pts)

Extract border-radius from buttons/inputs/cards/badges (cap 300). Round to nearest px.
PASS ≤4 unique, WARN 5-6, FAIL >6.

```js
(() => {
  const els = [...document.querySelectorAll('button, input, select, textarea, [class*="card"], [class*="Card"], [class*="badge"], [class*="Badge"], [class*="btn"], [class*="chip"], [class*="tag"], [role="button"]')]
    .filter(el => el.offsetParent !== null).slice(0, 300);
  const radii = new Map();
  for (const el of els) {
    const br = getComputedStyle(el).borderRadius;
    if (br && br !== '0px') {
      const normalized = br.replace(/[\d.]+px/g, m => Math.round(parseFloat(m)) + 'px');
      radii.set(normalized, (radii.get(normalized) || 0) + 1);
    }
  }
  const uniqueCount = radii.size;
  const status = uniqueCount <= 4 ? 'PASS' : uniqueCount <= 6 ? 'WARN' : 'FAIL';
  return {
    check: '3.7.6-border-radius', status, weight: 8,
    uniqueCount,
    values: [...radii.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([v, c]) => ({ radius: v, count: c })),
    elementsScanned: els.length
  };
})()
```

### 3.7.7 Typographic Scale Coherence (12pts)

Extract font-size/weight/family from text elements (cap 400). Test consecutive size ratios
against modular scales (1.25, 1.333, 1.5). PASS ≤5 sizes, WARN 6-7, FAIL >7. Override to
WARN if scale adherence <50%.

```js
(() => {
  const textEls = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,span,a,li,td,th,label,button,blockquote')]
    .filter(el => el.offsetParent !== null && el.textContent.trim().length > 0).slice(0, 400);
  const sizeMap = new Map();
  const weightSet = new Set();
  const familySet = new Set();
  for (const el of textEls) {
    const s = getComputedStyle(el);
    const size = Math.round(parseFloat(s.fontSize));
    sizeMap.set(size, (sizeMap.get(size) || 0) + 1);
    weightSet.add(s.fontWeight);
    const primary = s.fontFamily.split(',')[0].trim().replace(/['"]/g, '');
    familySet.add(primary);
  }
  const sizes = [...sizeMap.keys()].sort((a, b) => a - b);
  const scales = [1.125, 1.2, 1.25, 1.333, 1.414, 1.5, 1.618];
  let bestScale = null, bestAdherence = 0;
  for (const scale of scales) {
    let matches = 0;
    for (let i = 1; i < sizes.length; i++) {
      const ratio = sizes[i] / sizes[i - 1];
      if (Math.abs(ratio - scale) < 0.15 || Math.abs(ratio - 1) < 0.05) matches++;
    }
    const adherence = sizes.length > 1 ? Math.round((matches / (sizes.length - 1)) * 100) : 100;
    if (adherence > bestAdherence) { bestAdherence = adherence; bestScale = scale; }
  }
  let status = sizes.length <= 5 ? 'PASS' : sizes.length <= 7 ? 'WARN' : 'FAIL';
  if (status === 'PASS' && bestAdherence < 50) status = 'WARN';
  return {
    check: '3.7.7-typographic-scale', status, weight: 12,
    uniqueSizes: sizes.length, sizes,
    sizeDistribution: [...sizeMap.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([s, c]) => ({ size: s, count: c })),
    bestScale, scaleAdherence: bestAdherence,
    uniqueWeights: [...weightSet], uniqueFamilies: [...familySet],
    elementsScanned: textEls.length
  };
})()
```

### 3.7.8 Cognitive Load Index (12pts)

Composite: uniqueColors(bucketed to 32-unit steps)x0.3 + fontWeightsx0.2 + interactiveElementsx0.25
+ sectionsx0.15 + imagesx0.1. PASS CLI<12, WARN 12-20, FAIL >20.

```js
(() => {
  const visible = [...document.querySelectorAll('*')].filter(el => el.offsetParent !== null).slice(0, 300);
  const colorBuckets = new Set();
  for (const el of visible) {
    const s = getComputedStyle(el);
    for (const prop of ['color', 'backgroundColor']) {
      const m = s[prop].match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
      if (m) {
        const [r, g, b] = [m[1], m[2], m[3]].map(v => Math.round(+v / 32) * 32);
        if (!(r === 256 && g === 256 && b === 256) && !(r === 0 && g === 0 && b === 0))
          colorBuckets.add(`${r},${g},${b}`);
      }
    }
  }
  const weights = new Set(visible.slice(0, 100).map(el => getComputedStyle(el).fontWeight));
  const interactive = document.querySelectorAll('button, a[href], input, select, textarea, [role="button"], [onclick]').length;
  const sections = document.querySelectorAll('section, article, main, aside, nav, header, footer').length;
  const images = document.querySelectorAll('img, svg, video, canvas, [class*="icon"]').length;
  const cli = Math.round(
    colorBuckets.size * 0.3 + weights.size * 0.2 + interactive * 0.25 + sections * 0.15 + images * 0.1
  );
  const status = cli < 12 ? 'PASS' : cli <= 20 ? 'WARN' : 'FAIL';
  return {
    check: '3.7.8-cognitive-load', status, weight: 12,
    cli, components: {
      uniqueColors: colorBuckets.size, fontWeights: weights.size,
      interactiveElements: interactive, sections, images
    }
  };
})()
```

### 3.7.9 Alignment Grid Fidelity (8pts)

Sample left-edge X of content blocks (cap 50, above-fold only). Cluster edges within 8px
tolerance. Measure alignment percentage. PASS >=70%, WARN 50-69%, FAIL <50%.

```js
(() => {
  const viewportHeight = window.innerHeight;
  const blocks = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,ul,ol,section,article,div,form,table,blockquote')]
    .filter(el => {
      if (el.offsetParent === null) return false;
      const r = el.getBoundingClientRect();
      return r.top < viewportHeight && r.height > 20 && r.width > 50;
    })
    .slice(0, 50);
  if (blocks.length < 5) return { check: '3.7.9-alignment-grid', status: 'SKIP', weight: 8, reason: 'fewer than 5 above-fold blocks', blockCount: blocks.length };
  const leftEdges = blocks.map(el => Math.round(el.getBoundingClientRect().left));
  const clusters = [];
  for (const x of leftEdges) {
    const cluster = clusters.find(c => Math.abs(c.center - x) <= 8);
    if (cluster) {
      cluster.members++;
      cluster.center = Math.round((cluster.center * (cluster.members - 1) + x) / cluster.members);
    } else {
      clusters.push({ center: x, members: 1 });
    }
  }
  clusters.sort((a, b) => b.members - a.members);
  const alignedCount = clusters.slice(0, 3).reduce((s, c) => s + c.members, 0);
  const alignPct = Math.round((alignedCount / leftEdges.length) * 100);
  const status = alignPct >= 70 ? 'PASS' : alignPct >= 50 ? 'WARN' : 'FAIL';
  return {
    check: '3.7.9-alignment-grid', status, weight: 8,
    alignPct, totalBlocks: leftEdges.length,
    topClusters: clusters.slice(0, 5).map(c => ({ xPosition: c.center, count: c.members })),
    alignedToTop3: alignedCount
  };
})()
```

### 3.7.10 Semantic Color Proximity (7pts)

sRGB-to-CIELAB conversion (pure JS), deltaE between success/error/warning color pairs found via
class-name probing. PASS all pairs deltaE>=10, WARN 1 pair <10, FAIL >=2 pairs <10. SKIP if
semantic elements not found.

```js
(() => {
  function srgbToLab(r, g, b) {
    let [lr, lg, lb] = [r, g, b].map(c => {
      c = c / 255;
      return c > 0.04045 ? Math.pow((c + 0.055) / 1.055, 2.4) : c / 12.92;
    });
    let x = (lr * 0.4124564 + lg * 0.3575761 + lb * 0.1804375) / 0.95047;
    let y = (lr * 0.2126729 + lg * 0.7151522 + lb * 0.0721750);
    let z = (lr * 0.0193339 + lg * 0.1191920 + lb * 0.9503041) / 1.08883;
    [x, y, z] = [x, y, z].map(v => v > 0.008856 ? Math.cbrt(v) : (7.787 * v) + 16 / 116);
    return { L: 116 * y - 16, a: 500 * (x - y), b: 200 * (y - z) };
  }
  function deltaE(lab1, lab2) {
    return Math.sqrt((lab1.L - lab2.L) ** 2 + (lab1.a - lab2.a) ** 2 + (lab1.b - lab2.b) ** 2);
  }
  function parseColor(str) {
    const m = str.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    return m ? { r: +m[1], g: +m[2], b: +m[3] } : null;
  }
  const semanticProbes = {
    success: ['[class*="success"]', '[class*="Success"]', '.text-green', '.text-emerald', '[class*="positive"]'],
    error: ['[class*="error"]', '[class*="Error"]', '[class*="danger"]', '[class*="Danger"]', '.text-red', '[class*="destructive"]'],
    warning: ['[class*="warning"]', '[class*="Warning"]', '.text-yellow', '.text-amber', '[class*="caution"]'],
    info: ['[class*="info"]:not([class*="information"])', '[class*="Info"]', '.text-blue', '[class*="primary"]']
  };
  const found = {};
  for (const [role, selectors] of Object.entries(semanticProbes)) {
    for (const sel of selectors) {
      try {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) {
          const color = parseColor(getComputedStyle(el).color) || parseColor(getComputedStyle(el).backgroundColor);
          if (color && !(color.r === 0 && color.g === 0 && color.b === 0)) {
            found[role] = { ...color, selector: sel };
            break;
          }
        }
      } catch(e) {}
    }
  }
  const roles = Object.keys(found);
  if (roles.length < 2) return { check: '3.7.10-semantic-color', status: 'SKIP', weight: 7, reason: `only ${roles.length} semantic color(s) found`, found: roles };
  const pairs = [];
  let lowPairs = 0;
  for (let i = 0; i < roles.length; i++) {
    for (let j = i + 1; j < roles.length; j++) {
      const c1 = found[roles[i]], c2 = found[roles[j]];
      const lab1 = srgbToLab(c1.r, c1.g, c1.b);
      const lab2 = srgbToLab(c2.r, c2.g, c2.b);
      const de = Math.round(deltaE(lab1, lab2) * 10) / 10;
      if (de < 10) lowPairs++;
      pairs.push({ pair: `${roles[i]}/${roles[j]}`, deltaE: de, adequate: de >= 10 });
    }
  }
  const status = lowPairs === 0 ? 'PASS' : lowPairs === 1 ? 'WARN' : 'FAIL';
  const minDE = Math.min(...pairs.map(p => p.deltaE));
  return {
    check: '3.7.10-semantic-color', status, weight: 7,
    pairs, minDeltaE: minDE, lowPairs,
    colorsFound: Object.fromEntries(Object.entries(found).map(([k, v]) => [k, `rgb(${v.r},${v.g},${v.b})`]))
  };
})()
```

### 3.7.11 VDQS Aggregator

After running all 10 checks above, compute the composite Visual Design Quality Score:

```
For each check result:
  - PASS = full weight points
  - WARN = 50% of weight points
  - FAIL = 0 points
  - SKIP = excluded from denominator

VDQS = (earned points / applicable max points) * 100

Weights: Spacing 15, Rhythm 12, Elevation 8, Whitespace 10, Transition 8,
         Border-Radius 8, Typographic 12, Cognitive 12, Alignment 8, Semantic Color 7 = 100 total

Grade: A (90-100) | B (75-89) | C (60-74) | D (40-59) | F (<40)
```

Compute in-context after collecting all 10 results. No separate browser_evaluate call needed —
aggregate the returned JSON objects from checks 3.7.1–3.7.10.

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
| T1.8: Design Quality | | | | | |
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

## Visual Design Quality Score: {VDQS}/100 (Grade: {A-F})

### Design System Checks
| Check | Status | Key Metric | Notes |
|---|---|---|---|
| 1.8.1 Spacing Entropy | {status} | {n} unique values, {pct}% on-grid | |
| 1.8.2 Visual Rhythm | {status} | CV {value} | {n} blocks analyzed |
| 1.8.3 Elevation Layers | {status} | {n} unique shadows | |
| 1.8.4 Whitespace Breathing | {status} | {n}/{total} cards out of range | |
| 1.8.5 Transition Vocabulary | {status} | {n} unique easings | |
| 1.8.6 Border Radius | {status} | {n} unique values | |
| 1.8.7 Typographic Scale | {status} | {n} font sizes | |
| 1.8.8 Cognitive Load Index | {status} | CLI {value} | |
| 1.8.9 Alignment Grid | {status} | {pct}% aligned | |
| 1.8.10 Semantic Colors dE | {status} | Min dE {value} | |

### Design Quick Wins
{Top 3 easiest fixes from WARN/FAIL items — auto-prioritized by weight}

## Visual UX Quick Wins
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
