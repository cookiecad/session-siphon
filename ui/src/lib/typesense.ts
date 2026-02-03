/**
 * Typesense client library for Session Siphon.
 *
 * Provides search functionality for messages and conversations
 * stored in Typesense.
 */

// Configuration from environment or defaults
const TYPESENSE_HOST = process.env.NEXT_PUBLIC_TYPESENSE_HOST ?? "localhost";
const TYPESENSE_PORT = process.env.NEXT_PUBLIC_TYPESENSE_PORT ?? "8108";
const TYPESENSE_PROTOCOL = process.env.NEXT_PUBLIC_TYPESENSE_PROTOCOL ?? "http";
const TYPESENSE_API_KEY =
  process.env.NEXT_PUBLIC_TYPESENSE_API_KEY ?? "dev-api-key";

// Collection names
const MESSAGES_COLLECTION = "messages";
const CONVERSATIONS_COLLECTION = "conversations";

/**
 * Message document matching CanonicalMessage.to_typesense_doc()
 */
export interface Message {
  id: string;
  source: string;
  machine_id: string;
  project: string;
  conversation_id: string;
  ts: number;
  role: string;
  content: string;
  content_hash: string;
  raw_path: string;
  raw_offset: number;
}

/**
 * Conversation document matching Conversation.to_typesense_doc()
 */
export interface Conversation {
  id: string;
  source: string;
  machine_id: string;
  project: string;
  conversation_id: string;
  first_ts: number;
  last_ts: number;
  message_count: number;
  title: string;
  preview: string;
}

/**
 * Pagination options for search requests.
 */
export interface PaginationOptions {
  page?: number;
  perPage?: number;
}

/**
 * Filter options for message searches.
 */
export interface MessageFilters {
  source?: string;
  machineId?: string;
  project?: string;
  conversationId?: string;
  role?: string;
  startTs?: number;
  endTs?: number;
}

/**
 * Filter options for conversation searches.
 */
export interface ConversationFilters {
  source?: string;
  machineId?: string;
  project?: string;
  startTs?: number;
  endTs?: number;
}

/**
 * A single search hit with highlighting information.
 */
export interface SearchHit<T> {
  document: T;
  highlights: Array<{
    field: string;
    snippet: string;
    matchedTokens: string[];
  }>;
  textMatch: number;
}

/**
 * Paginated search results.
 */
export interface SearchResults<T> {
  hits: SearchHit<T>[];
  found: number;
  page: number;
  perPage: number;
  totalPages: number;
  facetCounts?: Record<string, Array<{ value: string; count: number }>>;
}

/**
 * Raw Typesense API response shape.
 */
interface TypesenseSearchResponse<T> {
  found: number;
  facet_counts?: Array<{
    field_name: string;
    counts: Array<{
      value: string;
      count: number;
    }>;
  }>;
  hits: Array<{
    document: T;
    highlights?: Array<{
      field: string;
      snippet?: string;
      matched_tokens?: string[];
    }>;
    text_match?: number;
  }>;
  page: number;
  request_params?: {
    per_page?: number;
  };
}

/**
 * Create the Typesense client configuration.
 */
export function getTypesenseConfig() {
  return {
    host: TYPESENSE_HOST,
    port: TYPESENSE_PORT,
    protocol: TYPESENSE_PROTOCOL,
    apiKey: TYPESENSE_API_KEY,
  };
}

/**
 * Get the base URL for Typesense API requests.
 */
function getBaseUrl(): string {
  return `${TYPESENSE_PROTOCOL}://${TYPESENSE_HOST}:${TYPESENSE_PORT}`;
}

/**
 * Build filter string from filter options.
 */
function buildMessageFilterString(filters: MessageFilters): string {
  const parts: string[] = [];

  if (filters.source) {
    parts.push(`source:=${filters.source}`);
  }
  if (filters.machineId) {
    parts.push(`machine_id:=${filters.machineId}`);
  }
  if (filters.project) {
    parts.push(`project:=${filters.project}`);
  }
  if (filters.conversationId) {
    parts.push(`conversation_id:=${filters.conversationId}`);
  }
  if (filters.role) {
    parts.push(`role:=${filters.role}`);
  }
  if (filters.startTs !== undefined) {
    parts.push(`ts:>=${filters.startTs}`);
  }
  if (filters.endTs !== undefined) {
    parts.push(`ts:<=${filters.endTs}`);
  }

  return parts.join(" && ");
}

/**
 * Build filter string from conversation filter options.
 */
function buildConversationFilterString(filters: ConversationFilters): string {
  const parts: string[] = [];

  if (filters.source) {
    parts.push(`source:=${filters.source}`);
  }
  if (filters.machineId) {
    parts.push(`machine_id:=${filters.machineId}`);
  }
  if (filters.project) {
    parts.push(`project:=${filters.project}`);
  }
  if (filters.startTs !== undefined) {
    parts.push(`last_ts:>=${filters.startTs}`);
  }
  if (filters.endTs !== undefined) {
    parts.push(`first_ts:<=${filters.endTs}`);
  }

  return parts.join(" && ");
}

/**
 * Execute a search request against Typesense.
 */
async function executeSearch<T>(
  collection: string,
  params: Record<string, string | number>
): Promise<TypesenseSearchResponse<T>> {
  const url = new URL(`${getBaseUrl()}/collections/${collection}/documents/search`);

  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, String(value));
  }

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: {
      "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Typesense search failed: ${response.status} ${error}`);
  }

  return response.json() as Promise<TypesenseSearchResponse<T>>;
}

/**
 * Transform Typesense response to our SearchResults format.
 */
function transformResponse<T>(
  response: TypesenseSearchResponse<T>,
  perPage: number
): SearchResults<T> {
  const hits: SearchHit<T>[] = response.hits.map((hit) => ({
    document: hit.document,
    highlights: (hit.highlights ?? []).map((h) => ({
      field: h.field,
      snippet: h.snippet ?? "",
      matchedTokens: h.matched_tokens ?? [],
    })),
    textMatch: hit.text_match ?? 0,
  }));

  const totalPages = Math.ceil(response.found / perPage);

  const facetCounts: Record<string, Array<{ value: string; count: number }>> = {};
  if (response.facet_counts) {
    for (const facet of response.facet_counts) {
      facetCounts[facet.field_name] = facet.counts;
    }
  }

  return {
    hits,
    found: response.found,
    page: response.page,
    perPage,
    totalPages,
    facetCounts,
  };
}

/**
 * Search messages by query string.
 *
 * @param query - The search query (use "*" for all documents)
 * @param filters - Optional filters to narrow results
 * @param pagination - Pagination options (page starts at 1)
 * @returns Paginated search results with highlighted matches
 *
 * @example
 * // Search for "authentication" in all messages
 * const results = await searchMessages("authentication");
 *
 * @example
 * // Search with filters and pagination
 * const results = await searchMessages("error", {
 *   source: "claude_code",
 *   role: "assistant",
 * }, { page: 2, perPage: 20 });
 */
export async function searchMessages(
  query: string,
  filters: MessageFilters = {},
  pagination: PaginationOptions = {}
): Promise<SearchResults<Message>> {
  const page = pagination.page ?? 1;
  const perPage = pagination.perPage ?? 10;

  const params: Record<string, string | number> = {
    q: query,
    query_by: "content",
    page,
    per_page: perPage,
    sort_by: "ts:desc",
  };

  const filterStr = buildMessageFilterString(filters);
  if (filterStr) {
    params.filter_by = filterStr;
  }

  const response = await executeSearch<Message>(MESSAGES_COLLECTION, params);
  return transformResponse(response, perPage);
}

/**
 * Search conversations by query string.
 *
 * @param query - The search query (use "*" for all documents)
 * @param filters - Optional filters to narrow results
 * @param pagination - Pagination options (page starts at 1)
 * @returns Paginated search results with highlighted matches
 *
 * @example
 * // List all conversations sorted by recency
 * const results = await searchConversations("*");
 *
 * @example
 * // Search conversations in a specific project
 * const results = await searchConversations("refactor", {
 *   project: "/home/user/myproject",
 * }, { page: 1, perPage: 25 });
 */
export async function searchConversations(
  query: string,
  filters: ConversationFilters = {},
  pagination: PaginationOptions = {}
): Promise<SearchResults<Conversation>> {
  const page = pagination.page ?? 1;
  const perPage = pagination.perPage ?? 10;

  const params: Record<string, string | number> = {
    q: query,
    query_by: "title,preview",
    page,
    per_page: perPage,
    sort_by: "last_ts:desc",
    facet_by: "source,project,machine_id",
    max_facet_values: 100, // Reasonable limit for dropdowns
  };

  const filterStr = buildConversationFilterString(filters);
  if (filterStr) {
    params.filter_by = filterStr;
  }

  const response = await executeSearch<Conversation>(
    CONVERSATIONS_COLLECTION,
    params
  );
  return transformResponse(response, perPage);
}

/**
 * Get all messages in a specific conversation.
 *
 * @param conversationId - The conversation ID to fetch messages for
 * @param pagination - Pagination options (page starts at 1)
 * @returns Paginated messages sorted by timestamp ascending
 *
 * @example
 * const messages = await getConversationMessages("abc123");
 */
export async function getConversationMessages(
  conversationId: string,
  pagination: PaginationOptions = {}
): Promise<SearchResults<Message>> {
  const page = pagination.page ?? 1;
  const perPage = pagination.perPage ?? 50;

  const params: Record<string, string | number> = {
    q: "*",
    query_by: "content",
    filter_by: `conversation_id:=${conversationId}`,
    page,
    per_page: perPage,
    sort_by: "ts:asc",
  };

  const response = await executeSearch<Message>(MESSAGES_COLLECTION, params);
  return transformResponse(response, perPage);
}

/**
 * Get a single message by ID.
 *
 * @param id - The message ID
 * @returns The message document or null if not found
 */
export async function getMessageById(id: string): Promise<Message | null> {
  const url = `${getBaseUrl()}/collections/${MESSAGES_COLLECTION}/documents/${encodeURIComponent(id)}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
      "Content-Type": "application/json",
    },
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Typesense fetch failed: ${response.status} ${error}`);
  }

  return response.json() as Promise<Message>;
}

/**
 * Get a single conversation by ID.
 *
 * @param id - The conversation ID
 * @returns The conversation document or null if not found
 */
export async function getConversationById(
  id: string
): Promise<Conversation | null> {
  const url = `${getBaseUrl()}/collections/${CONVERSATIONS_COLLECTION}/documents/${encodeURIComponent(id)}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
      "Content-Type": "application/json",
    },
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Typesense fetch failed: ${response.status} ${error}`);
  }

  return response.json() as Promise<Conversation>;
}
