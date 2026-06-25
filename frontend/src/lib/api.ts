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
  // E6/Wave Q1: best-effort WIIFM one-liner ("why you're seeing this"), when cached
  impact_headline?: string | null;
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
  has_gemini_key: boolean;
  gemini_key_verified: boolean;
  gemini_key_last4: string | null;
  gemini_key_verified_at: string | null;
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
export async function addFollow(kind: string, value: string): Promise<FollowItem> {
  return fetchJSON("/follows", { method: "POST", body: JSON.stringify({ kind, value }) });
}
export async function removeFollow(id: number): Promise<void> {
  await fetchJSON(`/follows/${id}`, { method: "DELETE" });
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
