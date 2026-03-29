"use client";

import { useState, useRef, useEffect } from "react";
import {
  Search,
  Scale,
  BookOpen,
  MessageSquare,
  Filter,
  Loader2,
  ExternalLink,
  ChevronDown,
  X,
  Sparkles,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = API.replace("http", "ws");

// ─── Types ────────────────────────────────────────────────────────

interface CaseResult {
  case_id: string;
  year: number;
  title: string;
  petitioner?: string;
  respondent?: string;
  date_of_judgment?: string;
  disposal_nature?: string;
  bench?: string;
  citation?: string;
  pdf_url?: string;
  chunk_text: string;
  score: number;
}

interface SearchResponse {
  query: string;
  results: CaseResult[];
  answer?: string;
  latency_ms: number;
  total_results: number;
}

// ─── Sub-components ───────────────────────────────────────────────

function CaseCard({ c, query }: { c: CaseResult; query: string }) {
  const [expanded, setExpanded] = useState(false);

  const highlightText = (text: string, q: string) => {
    if (!q) return text;
    const words = q.split(/\s+/).filter((w) => w.length > 3);
    if (words.length === 0) return text;
    const regex = new RegExp(`(${words.join("|")})`, "gi");
    return text.replace(regex, "<mark>$1</mark>");
  };

  return (
    <div className="border border-gray-200 rounded-xl p-5 hover:border-orange-300 hover:shadow-sm transition-all bg-white">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs font-medium bg-orange-50 text-orange-700 px-2 py-0.5 rounded-full">
              {c.year}
            </span>
            {c.disposal_nature && (
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  c.disposal_nature.toLowerCase().includes("allow")
                    ? "bg-green-50 text-green-700"
                    : c.disposal_nature.toLowerCase().includes("dismiss")
                    ? "bg-red-50 text-red-700"
                    : "bg-gray-100 text-gray-600"
                }`}
              >
                {c.disposal_nature}
              </span>
            )}
            {c.citation && (
              <span className="text-xs text-gray-500 font-mono">{c.citation}</span>
            )}
            <span className="text-xs text-gray-400 ml-auto">
              Score: {(c.score * 100).toFixed(1)}%
            </span>
          </div>

          <h3 className="font-semibold text-gray-900 text-sm leading-snug mb-1">
            {c.title || `${c.petitioner || "?"} vs ${c.respondent || "?"}`}
          </h3>

          {c.bench && (
            <p className="text-xs text-gray-500 mb-2">
              <span className="font-medium">Bench:</span> {c.bench}
            </p>
          )}

          {c.date_of_judgment && (
            <p className="text-xs text-gray-400 mb-3">{c.date_of_judgment}</p>
          )}

          <div
            className={`text-sm text-gray-600 leading-relaxed ${
              !expanded ? "line-clamp-3" : ""
            }`}
            dangerouslySetInnerHTML={{
              __html: highlightText(c.chunk_text, query),
            }}
          />

          <div className="flex items-center gap-3 mt-3">
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-orange-600 hover:text-orange-700 font-medium"
            >
              {expanded ? "Show less" : "Read more"}
            </button>
            {c.pdf_url && (
              <a
                href={`${API}/cases/${c.case_id}/pdf`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1"
              >
                <ExternalLink size={11} />
                View PDF
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Chat panel ───────────────────────────────────────────────────

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

function ChatPanel({ initialQuery }: { initialQuery: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState(initialQuery);
  const [isStreaming, setIsStreaming] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = () => {
    const q = input.trim();
    if (!q || isStreaming) return;

    const userMsg: ChatMessage = { role: "user", content: q };
    const assistantMsg: ChatMessage = { role: "assistant", content: "" };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setIsStreaming(true);

    const ws = new WebSocket(`${WS_URL}/chat`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          query: q,
          history: messages.slice(-6),
        })
      );
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "token") {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: updated[updated.length - 1].content + data.text,
          };
          return updated;
        });
      } else if (data.type === "done") {
        setIsStreaming(false);
        ws.close();
      }
    };

    ws.onerror = () => {
      setIsStreaming(false);
    };
    ws.onclose = () => {
      setIsStreaming(false);
    };
  };

  return (
    <div className="flex flex-col h-[600px] border border-gray-200 rounded-xl overflow-hidden bg-white">
      <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
        <MessageSquare size={16} className="text-orange-500" />
        <span className="text-sm font-medium text-gray-700">AI Legal Assistant</span>
        <span className="text-xs text-gray-400 ml-auto">Powered by Claude</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-sm text-gray-400 mt-8">
            <Scale size={32} className="mx-auto mb-3 text-gray-200" />
            <p>Ask any question about Indian Supreme Court judgments.</p>
            <p className="mt-1">e.g. "What is the basic structure doctrine?"</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm ${
                m.role === "user"
                  ? "bg-orange-500 text-white rounded-br-sm"
                  : "bg-gray-100 text-gray-800 rounded-bl-sm"
              }`}
            >
              {m.role === "assistant" ? (
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown>{m.content || "…"}</ReactMarkdown>
                </div>
              ) : (
                m.content
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="p-3 border-t border-gray-100">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder="Ask about a legal principle, case, or statute…"
            className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-300"
          />
          <button
            onClick={sendMessage}
            disabled={isStreaming || !input.trim()}
            className="bg-orange-500 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-orange-600 disabled:opacity-50 transition-colors"
          >
            {isStreaming ? <Loader2 size={16} className="animate-spin" /> : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [yearFilter, setYearFilter] = useState<string>("");
  const [disposalFilter, setDisposalFilter] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showChat, setShowChat] = useState(false);
  const [generateAnswer, setGenerateAnswer] = useState(false);
  const [availableYears, setAvailableYears] = useState<number[]>([]);

  useEffect(() => {
    fetch(`${API}/filters/years`)
      .then((r) => r.json())
      .then(setAvailableYears)
      .catch(() => {});
  }, []);

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const res = await fetch(`${API}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          year: yearFilter ? parseInt(yearFilter) : undefined,
          disposal: disposalFilter || undefined,
          generate_answer: generateAnswer,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: SearchResponse = await res.json();
      setResponse(data);
    } catch (err: any) {
      setError(err.message || "Search failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  const exampleQueries = [
    "Right to privacy as fundamental right",
    "Basic structure doctrine of Constitution",
    "Bail conditions in criminal cases",
    "Land acquisition compensation",
    "Article 370 abrogation",
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Scale className="text-orange-500" size={24} />
            <span className="font-bold text-gray-900 text-lg">India Court Search</span>
            <span className="text-xs text-gray-400 hidden sm:block ml-1">
              Supreme Court · 1950–2025 · AI-Powered
            </span>
          </div>
          <button
            onClick={() => setShowChat(!showChat)}
            className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg font-medium transition-colors ${
              showChat
                ? "bg-orange-100 text-orange-700"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            <MessageSquare size={15} />
            AI Chat
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Search hero */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Search Indian Supreme Court Judgments
          </h1>
          <p className="text-gray-500 text-sm">
            100,000+ judgments · Semantic AI search · Instant answers
          </p>
        </div>

        {/* Search form */}
        <form onSubmit={handleSearch} className="mb-6">
          <div className="flex gap-2 mb-3">
            <div className="relative flex-1">
              <Search
                size={18}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search judgments by legal principle, party name, statute, or topic…"
                className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 focus:border-transparent bg-white shadow-sm"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => { setQuery(""); setResponse(null); }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  <X size={16} />
                </button>
              )}
            </div>
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="bg-orange-500 text-white px-6 py-3 rounded-xl font-medium hover:bg-orange-600 disabled:opacity-50 transition-colors shadow-sm flex items-center gap-2 whitespace-nowrap"
            >
              {loading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Search size={16} />
              )}
              Search
            </button>
          </div>

          {/* Filters row */}
          <div className="flex items-center gap-3 flex-wrap">
            <Filter size={14} className="text-gray-400" />

            <select
              value={yearFilter}
              onChange={(e) => setYearFilter(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-orange-300"
            >
              <option value="">All years</option>
              {availableYears.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>

            <select
              value={disposalFilter}
              onChange={(e) => setDisposalFilter(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-orange-300"
            >
              <option value="">All disposals</option>
              <option value="Allowed">Allowed</option>
              <option value="Dismissed">Dismissed</option>
              <option value="Disposed">Disposed</option>
              <option value="Withdrawn">Withdrawn</option>
            </select>

            <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer ml-auto">
              <input
                type="checkbox"
                checked={generateAnswer}
                onChange={(e) => setGenerateAnswer(e.target.checked)}
                className="rounded"
              />
              <Sparkles size={13} className="text-orange-400" />
              Generate AI answer
            </label>
          </div>
        </form>

        {/* Example queries */}
        {!response && !loading && (
          <div className="mb-8">
            <p className="text-xs text-gray-400 mb-2">Try searching for:</p>
            <div className="flex flex-wrap gap-2">
              {exampleQueries.map((q) => (
                <button
                  key={q}
                  onClick={() => { setQuery(q); }}
                  className="text-xs bg-white border border-gray-200 text-gray-600 px-3 py-1.5 rounded-full hover:border-orange-300 hover:text-orange-600 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm mb-6">
            {error}
          </div>
        )}

        {/* Main content area */}
        <div className={`grid gap-6 ${showChat ? "lg:grid-cols-[1fr_400px]" : "grid-cols-1"}`}>
          {/* Results column */}
          <div>
            {response && (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <p className="text-sm text-gray-500">
                    <span className="font-medium text-gray-900">{response.total_results}</span>{" "}
                    results for &ldquo;{response.query}&rdquo;
                    <span className="text-gray-400 ml-2">· {response.latency_ms}ms</span>
                  </p>
                </div>

                {/* AI Answer */}
                {response.answer && (
                  <div className="bg-orange-50 border border-orange-200 rounded-xl p-5 mb-5">
                    <div className="flex items-center gap-2 mb-3">
                      <Sparkles size={15} className="text-orange-500" />
                      <span className="text-sm font-semibold text-orange-800">AI Answer</span>
                      <span className="text-xs text-orange-400 ml-auto">Powered by Claude</span>
                    </div>
                    <div className="prose prose-sm max-w-none text-gray-800">
                      <ReactMarkdown>{response.answer}</ReactMarkdown>
                    </div>
                  </div>
                )}

                {/* Case cards */}
                <div className="space-y-3">
                  {response.results.map((c) => (
                    <CaseCard key={`${c.case_id}-${c.score}`} c={c} query={query} />
                  ))}
                </div>

                {response.results.length === 0 && (
                  <div className="text-center py-12 text-gray-400">
                    <BookOpen size={40} className="mx-auto mb-3 text-gray-200" />
                    <p>No judgments found. Try a different search term.</p>
                  </div>
                )}
              </div>
            )}

            {!response && !loading && !error && (
              <div className="text-center py-16 text-gray-300">
                <Scale size={60} className="mx-auto mb-4" />
                <p className="text-gray-400 text-sm">
                  Search across 100,000+ Supreme Court judgments
                </p>
              </div>
            )}
          </div>

          {/* Chat column */}
          {showChat && (
            <div className="lg:sticky lg:top-20 lg:self-start">
              <ChatPanel initialQuery={query} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
