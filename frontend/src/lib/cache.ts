/* ═══════════════════════════════════════
   NewsLens client cache — two-tier stale-while-revalidate

   WHY: every screen used to fetch from zero on mount (data lived only in React state, discarded on
   navigation), so a cold Render backend meant a 3-min blank home and every "back to home" re-loaded.
   This cache lets a screen paint the LAST-KNOWN response instantly, then revalidate in the background.

   Two tiers:
   - in-memory Map  → instant, survives SPA navigation within one app session
   - persistent backend (IndexedDB via idb-keyval) → survives full app restarts (Firebase already uses
     IDB in this WebView, so it's a proven-persistent store here)

   In SSR / jsdom (no `indexedDB`) the default backend degrades to memory-only, so import never throws
   and server render simply behaves as a cold cache.
   ═══════════════════════════════════════ */

import {
  get as idbGet,
  set as idbSet,
  del as idbDel,
  entries as idbEntries,
  createStore,
  type UseStore,
} from "idb-keyval";

export interface CacheEntry<T> {
  data: T;
  /** ms epoch when written — drives TTL freshness checks and oldest-first eviction. */
  storedAt: number;
}

export interface PersistBackend {
  get<T>(key: string): Promise<CacheEntry<T> | undefined>;
  set<T>(key: string, entry: CacheEntry<T>): Promise<void>;
  del(key: string): Promise<void>;
  entries(): Promise<Array<[string, CacheEntry<unknown>]>>;
}

/** In-memory PersistBackend — the SSR/jsdom fallback and the test double. */
export function memoryBackend(): PersistBackend {
  const m = new Map<string, CacheEntry<unknown>>();
  return {
    async get<T>(key: string) {
      return m.get(key) as CacheEntry<T> | undefined;
    },
    async set<T>(key: string, entry: CacheEntry<T>) {
      m.set(key, entry as CacheEntry<unknown>);
    },
    async del(key: string) {
      m.delete(key);
    },
    async entries() {
      return [...m.entries()];
    },
  };
}

/** IndexedDB-backed PersistBackend. The store is created only when `indexedDB` exists, because
 *  idb-keyval's createStore opens the DB immediately and would throw under SSR/jsdom. (The static
 *  import above is inert at load time — only createStore touches IndexedDB.) */
function idbBackend(): PersistBackend {
  const s: UseStore = createStore("newslens-cache", "swr");
  return {
    get: <T,>(key: string) => idbGet<CacheEntry<T>>(key, s),
    set: <T,>(key: string, entry: CacheEntry<T>) => idbSet(key, entry, s),
    del: (key: string) => idbDel(key, s),
    entries: () => idbEntries(s) as Promise<Array<[string, CacheEntry<unknown>]>>,
  };
}

function defaultBackend(): PersistBackend {
  try {
    if (typeof indexedDB !== "undefined") return idbBackend();
  } catch {
    /* fall through to memory */
  }
  return memoryBackend();
}

let backend: PersistBackend = defaultBackend();
const memory = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

/* ── test seams ── */
export function _setBackend(b: PersistBackend): void {
  backend = b;
}
export function _resetCache(): void {
  memory.clear();
  inflight.clear();
}

/* ── TTL + eviction limits (namespace = key prefix before ":") ── */
/** Per-namespace hard TTL. Past this, an entry is a miss AND is pruned on the next write. */
export const CACHE_TTL_MS: Record<string, number> = {
  briefing: 6 * 60 * 60 * 1000, // a briefing is "today" — hold 6h
  cluster: 2 * 60 * 60 * 1000, // story detail — 2h
  feed: 30 * 60 * 1000, // firehose page — 30m
  topics: 60 * 60 * 1000,
  _default: 60 * 60 * 1000,
};
/** Overflow caps: evict oldest-written first once either is exceeded. */
export const CACHE_LIMITS = { maxEntries: 60, maxBytes: 4_000_000 };

function ttlFor(key: string): number {
  return CACHE_TTL_MS[key.split(":")[0]] ?? CACHE_TTL_MS._default;
}
function fresh(key: string, entry: CacheEntry<unknown>, maxAgeMs?: number): boolean {
  return maxAgeMs == null || Date.now() - entry.storedAt <= maxAgeMs;
}

/** Synchronous memory read — the instant-paint path. `undefined` = miss or stale. */
export function peek<T>(key: string, maxAgeMs?: number): T | undefined {
  const e = memory.get(key) as CacheEntry<T> | undefined;
  if (!e || !fresh(key, e, maxAgeMs)) return undefined;
  return e.data;
}

/** Async read: memory, then the persistent backend (hydrating memory on a hit). */
export async function load<T>(key: string, maxAgeMs?: number): Promise<T | undefined> {
  const hit = peek<T>(key, maxAgeMs);
  if (hit !== undefined) return hit;
  try {
    const e = await backend.get<T>(key);
    if (!e || !fresh(key, e, maxAgeMs)) return undefined;
    memory.set(key, e);
    return e.data;
  } catch {
    return undefined;
  }
}

/** Write-through both tiers, then evict stale/overflow entries. */
export async function store<T>(key: string, data: T): Promise<void> {
  const entry: CacheEntry<T> = { data, storedAt: Date.now() };
  memory.set(key, entry);
  trimMemory(); // bound the memory tier even if the persistent write below rejects (IDB quota)
  try {
    await backend.set(key, entry);
    await enforceLimits();
  } catch {
    /* best-effort persistence — the memory tier is already bounded by trimMemory() */
  }
}

/** Fetch fresh data, write it through, and return it. Concurrent calls for the same key share one
 *  in-flight request (dedupe); the slot is cleared on settle so a later call (or a retry after a
 *  rejection) fetches again. */
export function revalidate<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const p = fetcher()
    .then(async (data) => {
      await store(key, data);
      return data;
    })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, p);
  return p;
}

/** Prune expired entries (per-namespace TTL), then evict oldest-first until under the count/size caps.
 *  Runs on every write; entry counts are small (dozens), so the full-scan cost is negligible. */
async function enforceLimits(): Promise<void> {
  let all: Array<[string, CacheEntry<unknown>]>;
  try {
    all = await backend.entries();
  } catch {
    return;
  }
  const now = Date.now();

  // 1) TTL prune
  const live: Array<[string, CacheEntry<unknown>]> = [];
  for (const [k, e] of all) {
    if (now - e.storedAt > ttlFor(k)) {
      memory.delete(k);
      await backend.del(k);
    } else {
      live.push([k, e]);
    }
  }

  // 2) count + size cap → drop the oldest-written entries first, but never the sole newest entry
  //    (a single payload over the byte ceiling is kept, not self-evicted on the write that stored it).
  live.sort((a, b) => a[1].storedAt - b[1].storedAt);
  let total = live.reduce((s, [, e]) => s + entryBytes(e), 0);
  while (live.length > 1 && (live.length > CACHE_LIMITS.maxEntries || total > CACHE_LIMITS.maxBytes)) {
    const oldest = live.shift();
    if (!oldest) break;
    total -= entryBytes(oldest[1]);
    memory.delete(oldest[0]);
    await backend.del(oldest[0]);
  }
}

/** JSON byte estimate for an entry's payload (0 if it can't be serialized). */
function entryBytes(e: CacheEntry<unknown>): number {
  try {
    return JSON.stringify(e.data).length;
  } catch {
    return 0;
  }
}

/** Bound the in-memory tier independently of the persistent backend (which may reject writes on a
 *  quota-limited WebView, in which case enforceLimits never runs). TTL-prunes, then evicts oldest-first
 *  to the count/byte caps, always keeping the single newest entry so a lone oversized payload survives. */
function trimMemory(): void {
  const now = Date.now();
  for (const [k, e] of [...memory.entries()]) {
    if (now - e.storedAt > ttlFor(k)) memory.delete(k);
  }
  const live = [...memory.entries()].sort((a, b) => a[1].storedAt - b[1].storedAt);
  let total = live.reduce((s, [, e]) => s + entryBytes(e), 0);
  while (live.length > 1 && (live.length > CACHE_LIMITS.maxEntries || total > CACHE_LIMITS.maxBytes)) {
    const [k, e] = live.shift()!;
    total -= entryBytes(e);
    memory.delete(k);
  }
}
