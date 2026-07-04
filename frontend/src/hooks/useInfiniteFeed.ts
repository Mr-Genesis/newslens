"use client";

/**
 * WS-3 (#113): infinite feed pagination. The ONE shared hook for the home "All stories" feed and the
 * /feed screen — never copy this logic into a component.
 *
 * - Threads the server's `as_of` cursor: the first page pins it, later pages send it back so new
 *   ingest mid-scroll can't shift page boundaries (duplicate/drop). See GET /feed.
 * - Prefetches page N+1 as page N renders, so the next batch is usually already in hand on scroll.
 * - Appends with dedupe-by-id (belt-and-braces against any residual re-rank drift).
 * - Stale cursor: if the server hands back a FRESH cursor (its window went empty), reset and restart
 *   from page 1 with the new cursor.
 * - Terminal "done" once the window is exhausted; "error" is retryable.
 *
 *   mount ─▶ loadFirst(page1, no cursor) ─▶ pin as_of ─▶ prefetch(2)
 *   scroll ─▶ loadMore ─▶ await prefetch|fetch ─▶ [stale? reset+restart] ─▶ append ─▶ prefetch(N+1)
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { getFeed, type Article, type FeedResponse } from "@/lib/api";

export type FeedStatus = "loading" | "idle" | "paging" | "done" | "error";

interface Options {
  perPage?: number;
  topicId?: number;
  sourceType?: string;
}

export function useInfiniteFeed({ perPage = 20, topicId, sourceType }: Options = {}) {
  const [items, setItems] = useState<Article[]>([]);
  const [status, setStatusState] = useState<FeedStatus>("loading");
  const [total, setTotalState] = useState(0);

  const pageRef = useRef(0);                         // last successfully loaded page (0 = none yet)
  const asOfRef = useRef<string | null>(null);       // the pinned cursor
  const idsRef = useRef<Set<number>>(new Set());     // loaded article ids (dedupe)
  const prefetchRef = useRef<Promise<FeedResponse> | null>(null);  // page pageRef+1, in flight
  const statusRef = useRef<FeedStatus>("loading");   // synchronous guard (state is async)
  const mountedRef = useRef(true);
  const optsRef = useRef({ perPage, topicId, sourceType });
  optsRef.current = { perPage, topicId, sourceType };

  const setStatus = (s: FeedStatus) => {
    statusRef.current = s;
    if (mountedRef.current) setStatusState(s);
  };
  const setTotal = (t: number) => {
    if (mountedRef.current) setTotalState(t);
  };

  const fetchPage = useCallback((page: number): Promise<FeedResponse> => {
    const { perPage, topicId, sourceType } = optsRef.current;
    return getFeed(page, perPage, topicId, sourceType, asOfRef.current ?? undefined);
  }, []);

  // Kick off a prefetch and pre-attach a no-op catch so a page the user never scrolls to can't raise
  // an unhandledrejection — loadMore's own await still receives the rejection.
  const prefetch = useCallback((page: number): void => {
    const p = fetchPage(page);
    p.catch(() => {});
    prefetchRef.current = p;
  }, [fetchPage]);

  const hasMore = useCallback((resp: FeedResponse, page: number): boolean => {
    return resp.articles.length > 0 && page * optsRef.current.perPage < resp.total;
  }, []);

  const append = useCallback((arts: Article[]): void => {
    const fresh = arts.filter((a) => !idsRef.current.has(a.id));
    fresh.forEach((a) => idsRef.current.add(a.id));
    if (fresh.length && mountedRef.current) setItems((prev) => [...prev, ...fresh]);
  }, []);

  const loadFirst = useCallback(async (): Promise<void> => {
    setStatus("loading");
    try {
      const { perPage, topicId, sourceType } = optsRef.current;
      const resp = await getFeed(1, perPage, topicId, sourceType);  // first page: NO cursor (unfiltered)
      asOfRef.current = resp.as_of ?? null;
      pageRef.current = 1;
      append(resp.articles);
      setTotal(resp.total);
      if (hasMore(resp, 1)) {
        prefetch(2);
        setStatus("idle");
      } else {
        setStatus("done");
      }
    } catch {
      setStatus("error");
    }
  }, [append, hasMore, prefetch]);

  const loadMore = useCallback(async function loadMore(): Promise<void> {
    if (statusRef.current !== "idle") return;  // only page from a settled, has-more state (single-fire)
    setStatus("paging");
    const nextPage = pageRef.current + 1;
    let resp: FeedResponse;
    try {
      resp = await (prefetchRef.current ?? fetchPage(nextPage));
      prefetchRef.current = null;
    } catch {
      setStatus("error");
      return;
    }

    // Stale-cursor recovery: the server handed back a FRESH cursor (its pinned window went empty) →
    // drop what we have and restart pagination from page 1 with the new cursor.
    if (asOfRef.current && resp.as_of && resp.as_of !== asOfRef.current) {
      asOfRef.current = resp.as_of;
      pageRef.current = 0;
      idsRef.current.clear();
      prefetchRef.current = null;
      if (mountedRef.current) setItems([]);
      setStatus("idle");
      return loadMore();
    }

    pageRef.current = nextPage;
    append(resp.articles);
    setTotal(resp.total);
    if (hasMore(resp, nextPage)) {
      prefetch(nextPage + 1);
      setStatus("idle");
    } else {
      setStatus("done");
    }
  }, [append, fetchPage, hasMore, prefetch]);

  const loadMoreRef = useRef(loadMore);
  loadMoreRef.current = loadMore;

  const retry = useCallback((): void => {
    if (statusRef.current !== "error") return;
    if (pageRef.current === 0) void loadFirst();  // the first load failed
    else {
      setStatus("idle");
      void loadMore();  // a subsequent page failed
    }
  }, [loadFirst, loadMore]);

  // (Re)load on mount and whenever the query changes — full reset.
  useEffect(() => {
    mountedRef.current = true;
    pageRef.current = 0;
    asOfRef.current = null;
    idsRef.current = new Set();
    prefetchRef.current = null;
    setItems([]);
    void loadFirst();
    return () => {
      mountedRef.current = false;
    };
  }, [perPage, topicId, sourceType, loadFirst]);

  // The sentinel: when it scrolls into view (600px early), page in the next batch. The status guard in
  // loadMore makes repeated intersections while paging a no-op (single-fire).
  const observerRef = useRef<IntersectionObserver | null>(null);
  const sentinelRef = useCallback((el: HTMLElement | null) => {
    observerRef.current?.disconnect();
    if (!el || typeof IntersectionObserver === "undefined") return;
    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) void loadMoreRef.current();
      },
      { rootMargin: "600px" }
    );
    observerRef.current.observe(el);
  }, []);

  useEffect(() => () => observerRef.current?.disconnect(), []);

  return { items, status, total, sentinelRef, loadMore, retry };
}
