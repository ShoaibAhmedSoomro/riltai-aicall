# UI - Frontend Application

Next.js 15 frontend for the AICall voice AI platform.

## Project Structure

```
ui/
├── src/
│   ├── app/          # Next.js App Router pages
│   ├── components/   # React components
│   ├── lib/          # Utilities and configurations
│   ├── client/       # Auto-generated API client
│   ├── context/      # React context providers
│   ├── hooks/        # Custom React hooks
│   ├── constants/    # Application constants
│   └── types/        # TypeScript type definitions
├── public/           # Static assets
└── package.json
```

## Where to Find Things

| Looking for...      | Go to...                                             |
| ------------------- | ---------------------------------------------------- |
| Pages/routes        | `src/app/` - Next.js App Router (file-based routing) |
| Reusable components | `src/components/` - organized by feature             |
| Base UI primitives  | `src/components/ui/` - shadcn/ui components          |
| Workflow builder    | `src/components/flow/` - React Flow based            |
| API calls           | `src/client/` - auto-generated from OpenAPI spec     |
| Auth utilities      | `src/lib/auth/`                                      |
| Helper functions    | `src/lib/utils.ts`                                   |
| Global state        | `src/context/` - React context providers             |

## Tech Stack

- Next.js 15 with App Router, React 19, TypeScript
- Tailwind CSS with shadcn/ui components
- Zustand for state management
- @xyflow/react for workflow builder

## API Client

The `src/client/` directory is auto-generated from the backend OpenAPI spec. Whenever you add a
new api route in backend, and wish to use it in the UI, generate the client using below command.

```bash
npm run generate-client
```

### Regenerate as the last commit before you merge — never mid-branch

Two generated files are checked in and both are hard CI gates:

- `docs/api-reference/openapi.json`, dumped by `python -m scripts.dump_docs_openapi`. The
  pre-PR drift check fails on any diff.
- `ui/src/client/{types,sdk}.gen.ts` and `index.ts`, rewritten wholesale by `generate-client`.

Three things make the ordering matter rather than being a preference:

1. **`generate-client` needs a live backend.** `openapi-ts.config.ts` reads
   `${backendUrl}/api/v1/openapi.json` over HTTP, so it reflects whatever is running — not
   whatever is in your branch. Start the backend on your branch first, or you will regenerate
   against someone else's schema.
2. **It is a whole-file rewrite, not a patch.** Two branches that each add an endpoint conflict
   in a ~400 KB generated JSON every single time, in a file nobody hand-edits and nobody can
   sensibly review a conflict in.
3. **The dump has to come first.** `generate-client` reads the spec the running app serves;
   `dump_docs_openapi` writes the file CI compares against. Regenerating the client from a stale
   spec produces a client that passes locally and fails the drift gate.

So: do the work, and only when the branch is otherwise final, run both in this order and commit
the result as one final commit.

```bash
# with api/.env sourced and the backend running on your branch
python -m scripts.dump_docs_openapi
(cd ui && npm run generate-client)
git add docs/api-reference/openapi.json ui/src/client
git commit -m "chore: regenerate the API client"
```

Expect to redo this on every rebase. That is the cost of checking generated files in, and it is
cheaper than the alternative of not catching drift at all.

## Conventions

### File Uploads

Always use a hidden `<input type="file">` with a visible `<Button>` that triggers it via `fileInputRef.current?.click()`. Never use a visible `<Input type="file">` — the native file input styling is inconsistent and confusing. Show the selected filename next to or below the button.

### Authenticated API Calls

Components that make API calls must wait for auth to be ready before fetching. Use `useAuth()` and guard the `useEffect` with `authLoading` and `user`:

```tsx
const { user, loading: authLoading } = useAuth();
const hasFetched = useRef(false);

useEffect(() => {
  if (authLoading || !user || hasFetched.current) return;
  hasFetched.current = true;
  fetchData();
}, [authLoading, user]);
```

The auth interceptor (which attaches the Bearer token) is only registered once auth is fully loaded. Fetching before that sends unauthenticated requests that silently fail.

### API Error Handling

The generated client does **not** throw on HTTP error responses — it resolves to `{ data, error }`. A `try/catch` only catches network failures, so a 4xx/5xx slips through silently if you only check `response.data`. Always check `response.error`:

```tsx
const response = await someApiCall({ ... });
if (response.error) {
  setError(detailFromError(response.error, "Failed to save thing"));
  return;
}
// ...use response.data
```

Use `detailFromError` from `@/lib/apiError` to turn the error into a string — never render `error.detail` directly. FastAPI returns `detail` as a string for `HTTPException` but as an **array** of `{ msg, loc, ... }` objects for 422 validation errors; passing that array to React (`{error}`) crashes the page with "Objects are not valid as a React child". The helper normalizes both shapes and takes an optional fallback message.

## Development

```bash
npm install
npm run dev    # Runs on port 3000
```
