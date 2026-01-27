"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import {
  searchMessages,
  type Message,
  type SearchHit,
  type MessageFilters,
} from "@/lib/typesense";

interface SearchState {
  query: string;
  results: SearchHit<Message>[];
  total: number;
  page: number;
  totalPages: number;
  loading: boolean;
  error: string | null;
}

interface Filters {
  source: string;
  project: string;
  role: string;
}

const SOURCES = ["", "claude_code", "codex", "vscode_copilot", "gemini_cli"];
const ROLES = ["", "user", "assistant", "tool", "system"];

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function truncateContent(content: string, maxLength: number = 200): string {
  if (content.length <= maxLength) return content;
  return content.slice(0, maxLength) + "...";
}

function HighlightedSnippet({ snippet }: { snippet: string }) {
  // Typesense returns <mark> tags around matched text
  return (
    <span
      className="text-sm text-zinc-600 dark:text-zinc-400"
      dangerouslySetInnerHTML={{ __html: snippet }}
    />
  );
}

export default function SearchPage() {
  const [searchState, setSearchState] = useState<SearchState>({
    query: "",
    results: [],
    total: 0,
    page: 1,
    totalPages: 0,
    loading: false,
    error: null,
  });

  const [filters, setFilters] = useState<Filters>({
    source: "",
    project: "",
    role: "",
  });

  const [inputValue, setInputValue] = useState("");

  const executeSearch = useCallback(
    async (query: string, page: number = 1) => {
      if (!query.trim()) {
        setSearchState((prev) => ({
          ...prev,
          results: [],
          total: 0,
          page: 1,
          totalPages: 0,
          error: null,
        }));
        return;
      }

      setSearchState((prev) => ({ ...prev, loading: true, error: null }));

      try {
        const messageFilters: MessageFilters = {};
        if (filters.source) messageFilters.source = filters.source;
        if (filters.project) messageFilters.project = filters.project;
        if (filters.role) messageFilters.role = filters.role;

        const results = await searchMessages(query, messageFilters, {
          page,
          perPage: 20,
        });

        setSearchState({
          query,
          results: results.hits,
          total: results.found,
          page: results.page,
          totalPages: results.totalPages,
          loading: false,
          error: null,
        });
      } catch (err) {
        setSearchState((prev) => ({
          ...prev,
          loading: false,
          error: err instanceof Error ? err.message : "Search failed",
        }));
      }
    },
    [filters]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeSearch(inputValue, 1);
  };

  const handleFilterChange = (name: keyof Filters, value: string) => {
    setFilters((prev) => ({ ...prev, [name]: value }));
  };

  // Re-run search when filters change (if there's an active query)
  useEffect(() => {
    if (searchState.query) {
      executeSearch(searchState.query, 1);
    }
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= searchState.totalPages) {
      executeSearch(searchState.query, newPage);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <div className="mx-auto max-w-4xl px-4 py-8">
        <header className="mb-8">
          <Link
            href="/"
            className="text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            &larr; Back to Home
          </Link>
          <h1 className="mt-4 text-3xl font-semibold text-zinc-900 dark:text-zinc-50">
            Search Messages
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            Full-text search across all AI conversation messages
          </p>
        </header>

        {/* Search Form */}
        <form onSubmit={handleSubmit} className="mb-6">
          <div className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Search messages..."
              className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-3 text-zinc-900 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder-zinc-400"
            />
            <button
              type="submit"
              disabled={searchState.loading}
              className="rounded-lg bg-zinc-900 px-6 py-3 font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              {searchState.loading ? "Searching..." : "Search"}
            </button>
          </div>
        </form>

        {/* Faceted Filters */}
        <div className="mb-6 flex flex-wrap gap-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Source
            </label>
            <select
              value={filters.source}
              onChange={(e) => handleFilterChange("source", e.target.value)}
              className="rounded border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            >
              <option value="">All Sources</option>
              {SOURCES.filter(Boolean).map((source) => (
                <option key={source} value={source}>
                  {source.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Role
            </label>
            <select
              value={filters.role}
              onChange={(e) => handleFilterChange("role", e.target.value)}
              className="rounded border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            >
              <option value="">All Roles</option>
              {ROLES.filter(Boolean).map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-1 flex-col gap-1">
            <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Project
            </label>
            <input
              type="text"
              value={filters.project}
              onChange={(e) => handleFilterChange("project", e.target.value)}
              placeholder="Filter by project path..."
              className="rounded border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 placeholder-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500"
            />
          </div>
        </div>

        {/* Error Display */}
        {searchState.error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {searchState.error}
          </div>
        )}

        {/* Results Count */}
        {searchState.total > 0 && (
          <div className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
            Found {searchState.total.toLocaleString()} result
            {searchState.total !== 1 ? "s" : ""}
          </div>
        )}

        {/* Search Results */}
        <div className="space-y-4">
          {searchState.results.map((hit) => (
            <article
              key={hit.document.id}
              className="rounded-lg border border-zinc-200 bg-white p-4 transition-shadow hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded bg-zinc-100 px-2 py-0.5 font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                  {hit.document.source.replace(/_/g, " ")}
                </span>
                <span className="rounded bg-blue-100 px-2 py-0.5 font-medium text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
                  {hit.document.role}
                </span>
                <span className="text-zinc-500 dark:text-zinc-400">
                  {formatTimestamp(hit.document.ts)}
                </span>
              </div>

              <div className="mb-2">
                {hit.highlights.length > 0 && hit.highlights[0].snippet ? (
                  <HighlightedSnippet snippet={hit.highlights[0].snippet} />
                ) : (
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {truncateContent(hit.document.content)}
                  </p>
                )}
              </div>

              <div className="flex items-center justify-between text-xs">
                <span
                  className="max-w-xs truncate text-zinc-500 dark:text-zinc-500"
                  title={hit.document.project}
                >
                  {hit.document.project}
                </span>
                <Link
                  href={`/conversation/${encodeURIComponent(hit.document.conversation_id)}`}
                  className="font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                >
                  View Conversation &rarr;
                </Link>
              </div>
            </article>
          ))}
        </div>

        {/* Empty State */}
        {!searchState.loading &&
          searchState.query &&
          searchState.results.length === 0 &&
          !searchState.error && (
            <div className="py-12 text-center text-zinc-500 dark:text-zinc-400">
              No results found for &ldquo;{searchState.query}&rdquo;
            </div>
          )}

        {/* Pagination */}
        {searchState.totalPages > 1 && (
          <nav className="mt-8 flex items-center justify-center gap-2">
            <button
              onClick={() => handlePageChange(searchState.page - 1)}
              disabled={searchState.page === 1}
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              Previous
            </button>
            <span className="px-4 text-sm text-zinc-600 dark:text-zinc-400">
              Page {searchState.page} of {searchState.totalPages}
            </span>
            <button
              onClick={() => handlePageChange(searchState.page + 1)}
              disabled={searchState.page === searchState.totalPages}
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              Next
            </button>
          </nav>
        )}
      </div>
    </div>
  );
}
