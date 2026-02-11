# dev branch changelog

28 commits ahead of `main` — 61 files changed, +4955 / -844 lines.

---

## 1. Hook & reactivity fixes

- **useGameStream**: convert fallback from ref to state so React re-renders when snapshot data arrives
- **useReplayQueue**: clear `setTimeout` on unmount to prevent memory leaks
- **useGameAudio / useGameNarration**: move side effects out of render into `useEffect` to fix strict-mode double-fire
- **usePoll**: add `AbortController` to cancel in-flight fetches when URL changes or component unmounts, preventing race conditions

## 2. Spectator performance

- Consolidate timer and player-comment state updates to reduce re-renders during 500ms snapshot polling
- Remove fingerprint key on game lobby grid that caused full remount on every poll cycle

## 3. UI & accessibility

- Mobile hamburger menu for nav (responsive breakpoint, animated open/close)
- Skip-to-content link for keyboard navigation
- `<noscript>` fallback in scroll-reveal so content is visible with JS disabled
- Pagination: preserve sibling URL params (e.g. `lbPage` preserved when changing `rhPage`)

## 4. Error handling & loading states

- `global-error.tsx`, `not-found.tsx` for app-level boundaries
- `error.tsx` for `/(main)/` and `/game/[id]/` route segments
- `loading.tsx` for `/games`, `/leaderboard`, `/player/[username]`, `/game/[id]`, `/stream/[id]`

## 5. Design system

- Add spectator color tokens to `globals.css`: `chip-green`, `danger`, `dealer-gold`, `sb-blue`, `bb-purple`, `felt-green`, `warning`, `sage`, `felt-text`, `gold-muted`, `table-green`
- Replace ~40 hardcoded Tailwind hex values (`text-[#d4a843]`, etc.) across all spectator components with design token classes

## 6. Unified `/api/` routing

Full-stack migration to a consistent `/api/` path prefix:

| Package | Change |
|---------|--------|
| **server** | New unified game router under `/api/games` consolidating game, spectator, stream, and funding endpoints |
| **account-api** | `/accounts/*` → `/api/accounts/*` |
| **data-api** | Stream list path → `/api/games/{id}/streams` |
| **bot** | Client fetch URLs updated to `/api/` prefix |
| **frontend** (legacy) | Spectator HTML fetch URLs updated |
| **nu-front** | `next.config.ts` rewrites target `/api/`, client-side hooks (`use-game-stream`, `waiting-screen`, `game-lobby`) use `/api/` prefix |
| **infra** | ALB routing rules updated for `/api/` path-based routing |
| **tests** | All test suites updated to match new paths |
| **docs** | `instructions.md`, `ARCHITECTURE.md`, skill files updated |

## 7. Next.js 16 cache components (PPR)

- Enable `cacheComponents: true` in `next.config.ts` (replaces `experimental.ppr`)
- Migrate all data-fetching in `api.ts` from `next: { revalidate }` to `"use cache"` + `cacheLife()` + `cacheTag()`
- Cached functions handle errors internally (try/catch with fallback data) so builds succeed without an API server
- Games page wrapped in `<Suspense>` so static shell renders instantly via PPR while data streams in
- Build output confirms PPR active: dynamic routes show `◐ (Partial Prerender)`

## 8. Component quality

- **Shared icons**: extract duplicate X/GitHub/Telegram SVGs from nav + footer into `icons.tsx`
- **Hydration fixes**: `CopyrightYear` and `TimeAgo` client components for non-deterministic Date operations (wrapped in Suspense for Next.js 16 compatibility)
- **Features**: remove unnecessary `"use client"` directive — component has no hooks, now stays as RSC
- **Hero**: replace 16 `<Image>` instances with plain `<img>` for decorative chip elements (optimization overhead > benefit for identical decorative images)
- **Nav logo**: add `sizes="36px"` to prevent unnecessary srcset generation
- **FundingDot**: extract IIFE in WaitingScreen JSX into named component
- **React.memo**: wrap `GameCard` and `PlayerSeat` to skip re-renders during polling
- **Action log keys**: replace array index with composite `player-action-index` key for stable identity on reversed list

---

## Build verification

```
$ bun run build
▲ Next.js 16.1.6 (Turbopack, Cache Components)
✓ Compiled successfully

Route (app)             Revalidate  Expire
┌ ○ /
├ ○ /_not-found
├ ◐ /game/[id]
├ ○ /games                      3s      1y
├ ◐ /leaderboard
├ ◐ /player/[username]
└ ◐ /stream/[id]

○  (Static)             prerendered as static content
◐  (Partial Prerender)  prerendered with dynamic server-streamed content
```
