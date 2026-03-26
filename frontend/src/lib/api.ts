/* ═══════════════════════════════════════
   NewsLens API Client
   Calls go through Next.js rewrites → FastAPI
   ═══════════════════════════════════════ */

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}

/* ── Types ── */

export interface Source {
  id: number;
  name: string;
  url: string;
  is_paywalled: boolean;
}

export interface Article {
  id: number;
  title: string;
  url: string;
  snippet: string | null;
  ai_summary: string | null;
  published_at: string;
  fetched_at: string;
  source: Source;
  topics: Topic[];
  cluster_id: number | null;
}

export interface Topic {
  id: number;
  name: string;
  slug: string;
}

export interface BriefingStory {
  title: string;
  summary: string;
  cluster_id: number;
  category: string;
  source_count: number;
  coherence: number;
  is_read?: boolean;
}

export interface Briefing {
  stories: BriefingStory[];
  generated_at: string;
  explore_ratio?: number;
}

export interface ClusterDetail {
  id: number;
  title: string;
  summary: string | null;
  created_at: string;
  sources: ClusterSourceCard[];
}

export interface ClusterSourceCard {
  article: ArticleOut;
  is_free: boolean;
}

export interface ArticleOut {
  id: number;
  title: string;
  snippet: string | null;
  url: string;
  source: Source;
  published_at: string | null;
  embedding_status: string;
  source_count?: number;
  cluster_id?: number | null;
  has_ai_summary?: boolean;
}

export interface DiscoverCard {
  id: number;
  article_id: number;
  title: string;
  tension_line: string;
  facts: string[];
  sources: string[];
  topic_id: number;
  topic_name: string;
  coherence: number;
}

export interface FeedResponse {
  articles: Article[];
  total: number;
  page: number;
  per_page: number;
}

export interface TopicsResponse {
  your_topics: Topic[];
  explore_topics: Topic[];
  trending_topics: Topic[];
}

export interface HealthResponse {
  status: string;
  db: string;
}

/* ── Endpoints ── */

export async function getHealth(): Promise<HealthResponse> {
  return fetchJSON("/health");
}

export async function getBriefing(): Promise<Briefing> {
  return fetchJSON("/briefing");
}

export async function getFeed(
  page = 1,
  perPage = 20,
  topicId?: number
): Promise<FeedResponse> {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (topicId) params.set("topic", String(topicId));
  return fetchJSON(`/feed?${params}`);
}

export async function getCluster(clusterId: number): Promise<ClusterDetail> {
  return fetchJSON(`/clusters/${clusterId}`);
}

export async function getTopics(): Promise<TopicsResponse> {
  return fetchJSON("/topics");
}

export async function getDiscoverDeck(): Promise<DiscoverCard[]> {
  return fetchJSON("/discover/deck");
}

export async function recordSwipe(
  articleId: number,
  direction: "right" | "left" | "up"
): Promise<void> {
  await fetchJSON("/discover/swipe", {
    method: "POST",
    body: JSON.stringify({ article_id: articleId, direction }),
  });
}

export async function getTopicCards(
  topicId: number
): Promise<DiscoverCard[]> {
  return fetchJSON(`/discover/topic/${topicId}`);
}

export async function postFeedback(
  articleId: number,
  type: "interesting" | "less" | "save" | "share"
): Promise<void> {
  await fetchJSON("/feedback", {
    method: "POST",
    body: JSON.stringify({ article_id: articleId, feedback_type: type }),
  });
}

/* ── Settings ── */

export interface UserSettings {
  has_openai_key: boolean;
  openai_key_verified: boolean;
  openai_key_last4: string | null;
  openai_key_verified_at: string | null;
}

export interface KeyTestResult {
  success: boolean;
  error: string | null;
  models_available: number;
}

export async function getSettings(): Promise<UserSettings> {
  return fetchJSON("/settings");
}

export async function updateSettings(data: {
  openai_api_key: string | null;
}): Promise<UserSettings> {
  return fetchJSON("/settings", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function testApiKey(): Promise<KeyTestResult> {
  return fetchJSON("/settings/test-key", { method: "POST" });
}

/* ── Saved ── */

export interface SavedArticle {
  article_id: number;
  title: string;
  source_name: string;
  snippet: string | null;
  url: string;
  cluster_id: number | null;
  saved_at: string;
}

export interface SavedListResponse {
  articles: SavedArticle[];
  count: number;
}

export async function getSavedArticles(): Promise<SavedListResponse> {
  return fetchJSON("/saved");
}

export async function unsaveArticle(articleId: number): Promise<void> {
  await fetchJSON(`/saved/${articleId}`, { method: "DELETE" });
}

/* ── Stats ── */

export interface StatsResponse {
  articles_read: number;
  stories_saved: number;
  topics_explored: number;
}

export async function getStats(): Promise<StatsResponse> {
  return fetchJSON("/stats");
}
