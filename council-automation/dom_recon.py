"""DOM recon: run a real council query, save page HTML + screenshots for selector analysis.

Captures:
  1. Screenshot after council activation (before query)
  2. Screenshot after completion
  3. Full page HTML (for offline selector testing)
  4. DOM structure analysis JSON

Focus: find the correct selectors for individual model rows (GPT, Claude, Gemini)
that appear in council responses.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "council-automation"))

from council_browser import PerplexityCouncil, _log

RECON_JS = r"""() => {
    const results = {
        modelNameElements: [],
        expandablePanels: [],
        proseElements: [],
        buttonsWithModelText: [],
        councilSpecific: {},
    };
    const modelNames = ['GPT', 'Claude', 'Gemini', 'gpt', 'claude', 'gemini'];

    // Strategy 1: Walk ALL text nodes looking for model names
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const seen = new Set();
    while (walker.nextNode()) {
        const text = walker.currentNode.textContent.trim();
        if (!text || text.length > 300 || text.length < 2) continue;
        for (const name of modelNames) {
            if (text.toLowerCase().includes(name.toLowerCase()) && !seen.has(text.substring(0, 60))) {
                seen.add(text.substring(0, 60));
                const el = walker.currentNode.parentElement;
                if (!el) break;
                let ancestor = el;
                const chain = [];
                for (let i = 0; i < 10 && ancestor && ancestor !== document.body; i++) {
                    chain.push({
                        level: i,
                        tag: ancestor.tagName?.toLowerCase() || '',
                        id: ancestor.id || null,
                        classes: (ancestor.className?.toString() || '').substring(0, 250),
                        role: ancestor.getAttribute?.('role') || null,
                        ariaExpanded: ancestor.getAttribute?.('aria-expanded') || null,
                        ariaLabel: ancestor.getAttribute?.('aria-label') || null,
                        tabIndex: ancestor.getAttribute?.('tabindex') || null,
                        cursor: window.getComputedStyle(ancestor).cursor,
                        dataTestId: ancestor.getAttribute?.('data-testid') || null,
                        childCount: ancestor.children?.length || 0,
                        outerHTMLLen: ancestor.outerHTML?.length || 0,
                    });
                    ancestor = ancestor.parentElement;
                }
                results.modelNameElements.push({ text: text.substring(0, 150), chain });
                break;
            }
        }
    }

    // Strategy 2: aria-expanded panels
    document.querySelectorAll('[aria-expanded]').forEach(el => {
        const text = (el.textContent || '').trim();
        results.expandablePanels.push({
            tag: el.tagName.toLowerCase(),
            classes: (el.className?.toString() || '').substring(0, 250),
            text: text.substring(0, 200),
            ariaExpanded: el.getAttribute('aria-expanded'),
            role: el.getAttribute('role'),
            ariaLabel: el.getAttribute('aria-label'),
            id: el.id || null,
        });
    });

    // Strategy 3: Buttons/clickable with model names
    document.querySelectorAll('button, [role="button"], [tabindex="0"], [tabindex="-1"]').forEach(el => {
        const text = (el.textContent || '').trim();
        if (text.length < 300 && modelNames.some(n => text.toLowerCase().includes(n.toLowerCase()))) {
            results.buttonsWithModelText.push({
                tag: el.tagName.toLowerCase(),
                classes: (el.className?.toString() || '').substring(0, 250),
                text: text.substring(0, 200),
                role: el.getAttribute('role'),
                ariaExpanded: el.getAttribute('aria-expanded'),
                ariaLabel: el.getAttribute('aria-label'),
            });
        }
    });

    // Strategy 4: prose elements
    document.querySelectorAll('.prose, [class*="prose"]').forEach((el, i) => {
        if (i < 15) {
            results.proseElements.push({
                index: i,
                classes: (el.className?.toString() || '').substring(0, 250),
                textLen: (el.textContent || '').length,
                firstText: (el.textContent || '').trim().substring(0, 120),
                parentTag: el.parentElement?.tagName?.toLowerCase() || '',
                parentClasses: (el.parentElement?.className?.toString() || '').substring(0, 200),
            });
        }
    });

    // Strategy 5: Look for checkmark/completion indicators near model names
    results.councilSpecific.checkmarks = [];
    document.querySelectorAll('svg, [class*="check"], [class*="Check"], [class*="complete"], [class*="Complete"]').forEach(el => {
        const parent = el.parentElement;
        if (!parent) return;
        const nearbyText = parent.textContent?.trim()?.substring(0, 100) || '';
        if (modelNames.some(n => nearbyText.toLowerCase().includes(n.toLowerCase())) || el.closest('[aria-expanded]')) {
            results.councilSpecific.checkmarks.push({
                tag: el.tagName.toLowerCase(),
                classes: (el.className?.toString() || '').substring(0, 200),
                parentClasses: (parent.className?.toString() || '').substring(0, 200),
                nearbyText: nearbyText,
            });
        }
    });

    // Strategy 6: Look for collapsible sections / accordion patterns
    results.councilSpecific.accordions = [];
    document.querySelectorAll('[data-state], [data-open], [data-expanded]').forEach(el => {
        results.councilSpecific.accordions.push({
            tag: el.tagName.toLowerCase(),
            classes: (el.className?.toString() || '').substring(0, 200),
            state: el.getAttribute('data-state') || el.getAttribute('data-open') || el.getAttribute('data-expanded'),
            text: (el.textContent || '').trim().substring(0, 100),
        });
    });

    // Strategy 7: Look for model-specific container patterns
    // Council responses often have a repeated structure for each model
    results.councilSpecific.repeatedStructures = [];
    // Find sibling groups with similar class patterns
    const containers = document.querySelectorAll('div[class], section[class]');
    const classGroups = {};
    containers.forEach(el => {
        const cls = el.className?.toString() || '';
        if (cls.length > 10 && cls.length < 300) {
            const key = cls.substring(0, 80);
            if (!classGroups[key]) classGroups[key] = 0;
            classGroups[key]++;
        }
    });
    // Find classes that appear exactly 3 times (likely the 3 model containers)
    for (const [cls, count] of Object.entries(classGroups)) {
        if (count === 3) {
            const samples = document.querySelectorAll(`[class^="${cls.substring(0, 40)}"]`);
            results.councilSpecific.repeatedStructures.push({
                classPrefix: cls.substring(0, 80),
                count,
                sampleTexts: Array.from(samples).slice(0, 3).map(s =>
                    (s.textContent || '').trim().substring(0, 80)
                ),
            });
        }
    }

    return results;
}"""


async def main():
    query = (
        "Compare the architectural trade-offs between microservices and monolithic "
        "architectures for a construction industry SaaS application that needs real-time "
        "job costing, document processing, and multi-tenant data isolation. "
        "Consider deployment complexity, team size requirements, and data consistency guarantees."
    )

    recon_dir = Path.home() / ".claude" / "council-logs" / "dom-recon"
    recon_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M")

    _log(f"DOM Recon run {ts}")
    _log("Starting PerplexityCouncil (headful)...")

    council = PerplexityCouncil(headless=False, save_artifacts=True)
    try:
        await council.start()

        _log("Validating session...")
        if not await council.validate_session():
            print(json.dumps({"error": "Session expired"}))
            return

        page = await council.context.new_page()
        try:
            await page.goto("https://www.perplexity.ai/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Screenshot BEFORE activation
            ss1 = await page.screenshot(type="jpeg", quality=85)
            (recon_dir / f"{ts}_01_before_activation.jpg").write_bytes(ss1)
            _log("Saved: before_activation screenshot")

            # Activate council
            _log("Activating council...")
            activated = await council.activate_council(page)
            _log(f"Council activation reported: {activated}")

            # Screenshot AFTER activation, BEFORE query
            await page.wait_for_timeout(1000)
            ss2 = await page.screenshot(type="jpeg", quality=85)
            (recon_dir / f"{ts}_02_after_activation.jpg").write_bytes(ss2)
            _log("Saved: after_activation screenshot")

            # Submit query
            _log("Submitting query...")
            await council.submit_query(page, query)

            # Screenshot right after submit
            await page.wait_for_timeout(5000)
            ss3 = await page.screenshot(type="jpeg", quality=85)
            (recon_dir / f"{ts}_03_generating.jpg").write_bytes(ss3)
            _log("Saved: generating screenshot")

            # Wait for completion
            _log("Waiting for completion...")
            completed = await council.wait_for_completion(page)
            _log(f"Completed: {completed}")

            # Screenshot after completion
            ss4 = await page.screenshot(type="jpeg", quality=85)
            (recon_dir / f"{ts}_04_completed.jpg").write_bytes(ss4)
            _log("Saved: completed screenshot")

            # Full-page screenshot
            ss5 = await page.screenshot(type="jpeg", quality=85, full_page=True)
            (recon_dir / f"{ts}_05_full_page.jpg").write_bytes(ss5)
            _log("Saved: full_page screenshot")

            # Save full page HTML
            html = await page.content()
            (recon_dir / f"{ts}_page.html").write_text(html, encoding="utf-8")
            _log(f"Saved: page HTML ({len(html)} bytes)")

            # Run DOM recon JS
            _log("Running DOM recon JavaScript...")
            result = await page.evaluate(RECON_JS)
            (recon_dir / f"{ts}_recon.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
            _log(f"Saved: recon JSON")

            # Summary
            _log(f"Model name elements found: {len(result.get('modelNameElements', []))}")
            _log(f"Expandable panels found: {len(result.get('expandablePanels', []))}")
            _log(f"Buttons with model text: {len(result.get('buttonsWithModelText', []))}")
            _log(f"Prose elements: {len(result.get('proseElements', []))}")
            _log(f"Checkmarks near models: {len(result.get('councilSpecific', {}).get('checkmarks', []))}")
            _log(f"Accordion elements: {len(result.get('councilSpecific', {}).get('accordions', []))}")
            _log(f"3x repeated structures: {len(result.get('councilSpecific', {}).get('repeatedStructures', []))}")

            print(json.dumps(result, indent=2))

        finally:
            # Keep browser open for 10s to allow manual inspection
            _log("Keeping browser open 10s for manual inspection...")
            await page.wait_for_timeout(10000)
            await page.close()
    finally:
        await council.stop()


if __name__ == "__main__":
    asyncio.run(main())
