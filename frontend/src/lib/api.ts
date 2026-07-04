/* ═══════════════════════════════════════
   NewsLens API Client
   Calls go through Next.js rewrites → FastAPI
   Every helper routes through fetchJSON, so attaching the Firebase ID token here authenticates
   the whole app. getIdToken() returns null when signed out or server-side, so no header is sent
   and the backend serves the default user (back-compat during the multi-user rollout).
   ═══════════════════════════════════════ */

import { getIdToken } from "@/lib/firebase";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const doFetch = (token: string | null) =>
    fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });

  let res = await doFetch(await getIdToken());

  // Token expired/rotated since the cached copy (e.g. a long-idle tab) → force one refresh + retry.
  if (res.status === 401) {
    const fresh = await getIdToken(true);
    if (fresh) res = await doFetch(fresh);
  }

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
  // Phase 2 · #78 — gated-tier provenance (null for plain news sources).
  source_type?: string | null;
  author_name?: string | null;
  credibility_score?: number | null;
  is_preprint?: boolean;
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
  slug?: string; // not sent by GET /topics (TopicOut is id/name/article_count/is_explore)
  article_count?: number;
  is_explore?: boolean;
}

export interface BriefingStory {
  title: string;
  summary: string;
  /** null on the article-fallback path (article not clustered yet). */
  cluster_id: number | null;
  /** set on fallback stories so the card can open the single-article view (/story?aid=N). */
  article_id?: number | null;
  /** reader-facing region tag, e.g. "India" */
  region?: string | null;
  category: string;
  source_count: number;
  coherence: number;
  is_read?: boolean;
  // E6/Wave Q1: best-effort WIIFM one-liner ("why you're seeing this"), when cached
  impact_headline?: string | null;
  // Phase 2 · #78 — "research"/"expert" for a gated-tier story (→ RESEARCH/EXPERT badge). null for news.
  tier?: string | null;
}

export interface ArticleDetail {
  id: number;
  title: string;
  snippet: string | null;
  url: string;
  source_name: string;
  is_paywalled: boolean;
  published_at: string | null;
  /** resolved server-side — when set, the client upgrades to the full deep dive */
  cluster_id: number | null;
}

export function getArticle(id: number): Promise<ArticleDetail> {
  return fetchJSON(`/articles/${id}`);
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
  coherence: number;
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
  // Phase 2 · #83 — gated-tier opt-in surface: a research/expert card carries its source so the UI
  // can badge it and offer "Follow source". null/false for the news cards that fill the rest.
  source_id?: number | null;
  source_type?: string | null;
  is_gated?: boolean;
  is_preprint?: boolean;
  author_name?: string | null;
  credibility_score?: number | null;
}

export interface FeedResponse {
  articles: Article[];
  total: number;
  page: number;
  per_page: number;
  // WS-3 (#113): the pagination cursor. First response = now(); thread it back on later pages to pin
  // the pool (fetched_at <= as_of). A stale cursor comes back refreshed so the client can restart.
  as_of: string;
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
  topicId?: number,
  // Phase 2 · #82 — source-type filter: "news" | "research" | "expert" (omit/"all" = every tier).
  sourceType?: string,
  // WS-3 (#113) — pagination cursor. URLSearchParams encodes the "+00:00"/"Z" offset safely.
  asOf?: string
): Promise<FeedResponse> {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (topicId) params.set("topic", String(topicId));
  if (sourceType && sourceType !== "all") params.set("source_type", sourceType);
  if (asOf) params.set("as_of", asOf);
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

/* ── WS-1 (#111): impressions + dwell ── */

export type ImpressionItem = {
  cluster_id?: number | null;
  article_id?: number | null;
  surface: "briefing" | "feed" | "rail" | "discover" | "search";
};

/** Batched, fire-and-forget: what the user SAW. Server dedupes per day + caps volume.
 *  `keepalive` (exit paths: pagehide/unmount) lets the request outlive page teardown so the final
 *  batch isn't cancelled by the browser mid-flight (review C4/C6). Batches are far under the 64KB
 *  keepalive budget. */
export async function postImpressions(items: ImpressionItem[], keepalive = false): Promise<void> {
  if (!items.length) return;
  await fetchJSON("/impressions", {
    method: "POST",
    body: JSON.stringify({ items }),
    keepalive,
  });
}

/** Dwell: recorded on story close against the cluster's auto-read row (server-side GREATEST). */
export async function postDwell(
  clusterId: number,
  durationMs: number,
  surface: ImpressionItem["surface"],
  keepalive = false
): Promise<void> {
  await fetchJSON("/feedback", {
    method: "POST",
    keepalive, // survive teardown when fired from pagehide/visibility-hidden
    body: JSON.stringify({
      // article_id is schema-required but ignored for the dwell target (server resolves the
      // cluster's canonical read row); pass the cluster id to satisfy the field.
      article_id: clusterId,
      feedback_type: "read",
      cluster_id: clusterId,
      duration_ms: Math.max(0, Math.round(durationMs)),
      surface,
    }),
  });
}

/* ── Settings ── */

export interface UserSettings {
  has_openai_key: boolean;
  openai_key_verified: boolean;
  openai_key_last4: string | null;
  openai_key_verified_at: string | null;
  has_gemini_key: boolean;
  gemini_key_verified: boolean;
  gemini_key_last4: string | null;
  gemini_key_verified_at: string | null;
  has_anthropic_key: boolean;
  anthropic_key_verified: boolean;
  anthropic_key_last4: string | null;
  anthropic_key_verified_at: string | null;
  active_provider: string | null;
  model_prefs: Record<string, string>;
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
  openai_api_key?: string | null;
  active_provider?: string;
  model_prefs?: Record<string, string>;
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

/* ── Profile (E3) ── */

export interface Profile {
  profession: string | null;
  locale: string;
  interests: string[];
  depth_pref?: string; // brief | standard | expert
  region?: string | null;
}

export async function getProfile(): Promise<Profile> {
  return fetchJSON("/profile");
}

export async function updateProfile(
  data: Partial<{
    profession: string | null;
    locale: string;
    interests: string[];
    depth_pref: string;
    region: string | null;
  }>
): Promise<Profile> {
  return fetchJSON("/profile", { method: "PUT", body: JSON.stringify(data) });
}

/* ── Gemini key (E1) ── */

export async function setGeminiKey(
  gemini_api_key: string | null
): Promise<{ has_gemini_key: boolean }> {
  return fetchJSON("/settings/gemini-key", {
    method: "PUT",
    body: JSON.stringify({ gemini_api_key }),
  });
}

export async function testGeminiKey(): Promise<KeyTestResult> {
  return fetchJSON("/settings/test-gemini-key", { method: "POST" });
}

export async function setAnthropicKey(
  anthropic_api_key: string | null
): Promise<{ has_anthropic_key: boolean }> {
  return fetchJSON("/settings/anthropic-key", {
    method: "PUT",
    body: JSON.stringify({ anthropic_api_key }),
  });
}

export async function testAnthropicKey(): Promise<KeyTestResult> {
  return fetchJSON("/settings/test-anthropic-key", { method: "POST" });
}

/* ── Cluster lenses (E5/E6/E7/E8) ── */

export interface LensResult {
  cached?: boolean;
  unavailable?: boolean;
  reason?: string;
  error?: string;
  [key: string]: unknown;
}

export type AnalysisLens = "key_facts" | "5ws" | "profession";
export type Difficulty = "easy" | "medium" | "hard";

export async function getClusterAnalysis(
  clusterId: number,
  lens: AnalysisLens
): Promise<LensResult> {
  return fetchJSON(`/clusters/${clusterId}/analysis?lens=${lens}`);
}

/* Impact engine v2 (Wave A) — structured StoryImpact contract */
export type Horizon = "now" | "weeks" | "quarter" | "year_plus";
export type ImpactConfidence = "low" | "medium" | "high";

export interface ImpactEvidence {
  claim: string;
  source: string;
}

export interface ImpactDimension {
  applicable: boolean;
  relevance: string;
  mechanism: string;
  watch_items: string[];
  horizon: Horizon;
  confidence: ImpactConfidence;
  confidence_rationale: string;
  evidence: ImpactEvidence[];
  not_advice?: boolean;
}

export interface StoryImpact {
  cluster_id: string;
  headline: string;
  personal_relevance: { score: number; one_liner: string };
  dimensions: {
    professional: ImpactDimension;
    financial: ImpactDimension;
    civic: ImpactDimension;
  };
  caveats: string;
  cached?: boolean;
}

export interface Unavailable {
  unavailable: true;
  reason?: string;
}

export type ImpactResult = StoryImpact | Unavailable;

/** Type guard: a real impact payload (vs an `unavailable` degradation response). */
export function isStoryImpact(r: ImpactResult | null): r is StoryImpact {
  return !!r && !("unavailable" in r) && "personal_relevance" in r;
}

export async function getClusterImpact(clusterId: number): Promise<ImpactResult> {
  return fetchJSON(`/clusters/${clusterId}/impact`);
}

/* Ask this story (Wave B1) */
export interface AskCitation {
  claim: string;
  source: string;
}
export interface AskAnswer {
  answer: string;
  citations: AskCitation[];
  refused: boolean;
}
export type AskResult = AskAnswer | Unavailable;

export function isAskAnswer(r: AskResult): r is AskAnswer {
  return !("unavailable" in r);
}

export async function askStory(clusterId: number, question: string): Promise<AskResult> {
  return fetchJSON(`/clusters/${clusterId}/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

/* Frameworks (B2) + Consensus (B3) */
export interface FrameworkChip {
  id: string;
  label: string;
  one_liner: string;
}
export interface FrameworksResult {
  story_type?: string;
  frameworks?: FrameworkChip[];
  unavailable?: boolean;
}
export async function getFrameworks(clusterId: number): Promise<FrameworksResult> {
  return fetchJSON(`/clusters/${clusterId}/frameworks`);
}

// G1 entity backbone
export interface ClusterEntity {
  id: number;
  canonical_name: string;
  kind: string;
  salience: number;
}
export async function getClusterEntities(clusterId: number): Promise<ClusterEntity[]> {
  return fetchJSON(`/clusters/${clusterId}/entities`);
}

export interface EntityCluster {
  cluster_id: number;
  title: string;
  created_at: string;
}
export async function getEntityClusters(entityId: number): Promise<EntityCluster[]> {
  return fetchJSON(`/entities/${entityId}/clusters`);
}

export interface Dissent {
  outlet: string;
  point: string;
}
export interface ConsensusResult {
  agree_count?: number;
  total?: number;
  dissent?: Dissent[];
  summary?: string;
  unavailable?: boolean;
}
export async function getConsensus(clusterId: number): Promise<ConsensusResult> {
  return fetchJSON(`/clusters/${clusterId}/consensus`);
}

/* Wave C: digest + follows */
export interface DigestStory {
  cluster_id: number;
  title: string;
  headline: string | null;
}
export interface Digest {
  count: number;
  since: string;
  items: DigestStory[];
}
export async function getDigest(): Promise<Digest> {
  return fetchJSON("/digest");
}

export interface FollowItem {
  id: number;
  kind: string;
  value: string;
}
export async function getFollows(): Promise<FollowItem[]> {
  return fetchJSON("/follows");
}
export async function addFollow(kind: string, value: string, entityId?: number): Promise<FollowItem> {
  return fetchJSON("/follows", {
    method: "POST",
    // G2: pass the tapped chip's entity_id so the follow links to a real graph node (+ seeds relevance).
    body: JSON.stringify({ kind, value, ...(entityId != null ? { entity_id: entityId } : {}) }),
  });
}
export async function removeFollow(id: number): Promise<void> {
  await fetchJSON(`/follows/${id}`, { method: "DELETE" });
}

/* ── WS-2 (#112): "News You Follow" rails ── */
export interface RailStory {
  cluster_id: number;
  title: string;
  summary: string | null;
  source_count: number;
}
export interface FollowRail {
  follow_id: number;
  kind: string;
  value: string;
  total: number;
  new_count: number;
  stories: RailStory[];
}
export async function getFollowRails(): Promise<FollowRail[]> {
  const r = await fetchJSON<{ rails: FollowRail[] }>("/follows/rails");
  return r.rails ?? [];
}
/** Clear a rail's "N new" badge (tapping a rail story or its "see all"). */
export async function markFollowSeen(followId: number): Promise<void> {
  await fetchJSON(`/follows/${followId}/seen`, { method: "POST" });
}

export async function getClusterStrategic(clusterId: number): Promise<LensResult> {
  return fetchJSON(`/clusters/${clusterId}/strategic`);
}

export async function getClusterTrivia(
  clusterId: number,
  difficulty: Difficulty = "medium"
): Promise<LensResult> {
  return fetchJSON(`/clusters/${clusterId}/trivia?difficulty=${difficulty}`);
}

export async function getDailyTrivia(
  topic = "world news",
  difficulty: Difficulty = "medium"
): Promise<LensResult> {
  return fetchJSON(
    `/trivia/daily?topic=${encodeURIComponent(topic)}&difficulty=${difficulty}`
  );
}

/* ── Search (E4) ── */

export interface SearchResultItem {
  id: number;
  title: string;
  snippet: string | null;
  url: string;
  source: Source;
  cluster_id: number | null;
  matched_on: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResultItem[];
}

export async function search(q: string): Promise<SearchResponse> {
  return fetchJSON(`/search?q=${encodeURIComponent(q)}`);
}

/* ── Admin sources (E2) ── */

export interface AdminSource {
  id: number;
  name: string;
  url: string;
  rss_url: string | null;
  region: string | null;
  category: string | null;
  is_paywalled: boolean;
  source_type: string | null;
}

export async function getAdminSources(): Promise<AdminSource[]> {
  return fetchJSON("/admin/sources");
}

export async function createAdminSource(data: {
  name: string;
  url: string;
  rss_url?: string;
  region?: string;
  category?: string;
}): Promise<{ id: number; name: string }> {
  return fetchJSON("/admin/sources", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
