import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Every page under /auth must be reachable while signed out.
 *
 * The password-reset pages shipped redirecting to the login form for anyone not
 * signed in, because middleware.ts keeps its own allowlist and nobody added
 * them. They worked in every manual check -- all of which were made while
 * signed in, the one state in which nobody needs a reset link.
 *
 * Reads the source rather than importing the middleware: it pulls in the
 * server runtime, and the thing under test is a list, not behaviour.
 */

const SRC = resolve(process.cwd(), 'src');

function publicPaths(): string[] {
    const source = readFileSync(resolve(SRC, 'middleware.ts'), 'utf8');
    const block = source.match(/const PUBLIC_PATHS = \[([\s\S]*?)\];/);
    if (!block) throw new Error('PUBLIC_PATHS not found in middleware.ts');
    return [...block[1].matchAll(/'([^']+)'/g)].map((m) => m[1]);
}

function authPages(): string[] {
    const root = resolve(SRC, 'app', 'auth');
    return readdirSync(root, { withFileTypes: true })
        .filter((d) => d.isDirectory())
        .filter((d) =>
            readdirSync(resolve(root, d.name)).some((f) => /^page\.(t|j)sx?$/.test(f)),
        )
        .map((d) => `/auth/${d.name}`);
}

describe('middleware public paths', () => {
    it('lists every page under /auth', () => {
        const listed = publicPaths();
        const missing = authPages().filter((p) => !listed.includes(p));
        expect(missing, `signed-out users are redirected away from: ${missing.join(', ')}`).toEqual([]);
    });

    it('still knows about the pages this was written for', () => {
        // Guards the guard: an empty directory scan would make the test above
        // pass vacuously.
        expect(authPages()).toEqual(
            expect.arrayContaining([
                '/auth/login',
                '/auth/signup',
                '/auth/forgot-password',
                '/auth/reset-password',
                '/auth/verify-email',
            ]),
        );
    });
});
