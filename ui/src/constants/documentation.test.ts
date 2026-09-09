// @vitest-environment node
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import * as docs from "./documentation";

/**
 * Documentation links, which fail in the two quietest ways a link can.
 *
 * 1. **The host does not exist.** `docs.rilt.ai` is NXDOMAIN and nothing in
 *    this repo deploys it, so every "Learn more" in the product was a browser
 *    error page — shipped, in production, with no test and no error anywhere.
 *
 * 2. **The page does not exist.** A link can resolve and still 404 because the
 *    route was renamed or never written. Nothing else checks that the path on
 *    the end of a documentation URL corresponds to a real page.
 *
 * Both are invisible in CI, in the type checker, and in review. So they are
 * asserted here against the `docs/` sources that are the actual content.
 */

const REPO_ROOT = resolve(__dirname, "..", "..", "..");
const DOCS_DIR = join(REPO_ROOT, "docs");

/** Every documentation URL the product can produce. */
function allDocUrls(): string[] {
    const urls: string[] = [];
    for (const value of Object.values(docs)) {
        if (typeof value === "string") {
            urls.push(value);
        } else if (value && typeof value === "object") {
            for (const nested of Object.values(value)) {
                if (typeof nested === "string") urls.push(nested);
            }
        }
    }
    return [...new Set(urls)];
}

/** The `docs/`-relative route a URL points at, anchor stripped. "" is the root. */
function routeFor(url: string): string {
    const withoutAnchor = url.split("#")[0];
    // The documentation root, in either form, addresses no page of its own.
    if (withoutAnchor === docs.DOCS_BASE) return "";
    // Source form: .../blob/<ref>/docs/<route>.mdx
    const source = withoutAnchor.match(/\/blob\/[^/]+\/docs\/(.+)\.mdx$/);
    if (source) return source[1];
    // Published form: https://docs.example.com/<route>
    return new URL(withoutAnchor).pathname.replace(/^\/+|\/+$/g, "");
}

function walk(dir: string): string[] {
    const out: string[] = [];
    for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
            if (entry === "node_modules" || entry === ".next") continue;
            out.push(...walk(full));
        } else {
            out.push(full);
        }
    }
    return out;
}

describe("documentation links", () => {
    it("produces at least one URL per documented surface", () => {
        // Guards the reflection above: if the module were restructured so that
        // Object.values no longer reached the constants, every other test here
        // would pass vacuously on an empty list.
        expect(allDocUrls().length).toBeGreaterThan(20);
    });

    it("every link points at a page that actually exists", () => {
        const missing: string[] = [];
        for (const url of allDocUrls()) {
            const route = routeFor(url);
            if (!route) continue; // the docs root
            const candidates = [
                join(DOCS_DIR, `${route}.mdx`),
                join(DOCS_DIR, route, "index.mdx"),
            ];
            if (!candidates.some(existsSync)) {
                missing.push(`${route}  (from ${url})`);
            }
        }
        expect(missing, `documentation links with no page:\n${missing.join("\n")}`).toEqual(
            [],
        );
    });

    it("resolves to a host that is actually published", () => {
        // docs.rilt.ai does not resolve. If someone points DOCS_SITE at it
        // before the DNS record and the Mintlify deploy exist, this fails
        // rather than shipping dead links again.
        const PUBLISHED_HOSTS = ["github.com"];
        for (const url of allDocUrls()) {
            const host = new URL(url).host;
            expect(
                PUBLISHED_HOSTS,
                `${host} is not in the published-hosts list. If the docs site is now ` +
                    `live, add its host here in the same commit that sets DOCS_SITE.`,
            ).toContain(host);
        }
    });

    it("has no documentation URL hardcoded outside this module", () => {
        // Twelve of these were literals in feature files, which is why they all
        // had to be found by grep rather than changed in one place.
        const offenders: string[] = [];
        for (const file of walk(join(REPO_ROOT, "ui", "src"))) {
            if (!/\.tsx?$/.test(file)) continue;
            if (file.endsWith("documentation.ts") || file.endsWith("documentation.test.ts")) {
                continue;
            }
            if (/docs\.rilt\.ai|\/blob\/main\/docs/.test(readFileSync(file, "utf8"))) {
                offenders.push(file.slice(REPO_ROOT.length + 1));
            }
        }
        expect(
            offenders,
            `import from @/constants/documentation instead:\n${offenders.join("\n")}`,
        ).toEqual([]);
    });

    it("keeps anchors when building a URL", () => {
        const url = docs.docsUrl("voice-agent/add-to-website#headless-mode");
        expect(url).toContain("#headless-mode");
        expect(url).toContain("add-to-website");
    });

    it("returns the root for an empty path rather than a trailing slash", () => {
        expect(docs.docsUrl("")).toBe(docs.DOCS_BASE);
        expect(docs.DOCS_BASE.endsWith("/")).toBe(false);
    });
});
