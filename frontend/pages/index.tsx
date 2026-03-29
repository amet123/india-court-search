"use client";
import { useState, useEffect } from "react";
import { Search, Scale, Loader2, X, Sparkles, ExternalLink } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

function CaseCard({ c, query }: { c: CaseResult; query: string }) {
  const [expanded, setExpanded] = useState(false);
  const highlight = (text: string) => {
    if (!query) return text;
    const words = query.split(/\s+/).filter(w => w.length > 3);
    if (!words.length) return text;
    return text.replace(new RegExp(`(${words.join("|")})`, "gi"), "<mark>$1</mark>");
  };
  return (
    <div className="border border-gray-200 rounded-xl p-5 hover:border-orange-300 hover:shadow-sm transition-all bg-white">
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="text-xs font-medium bg-orange-50 text-orange-700 px-2 py-0.5 rounded-full">{c.year}</span>
        {c.disposal_nature && (
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            c.disposal_nature.toLowerCase().includes("allow") ? "bg-green-50 text-green-700" :
            c.disposal_nature.toLowerCase().includes("dismiss") ? "bg-red-50 text-red-700" :
            "bg-gray-100 text-gray-600"}`}>{c.disposal_nature}</span>
        )}
        {c.citation && <span className="text-xs text-gray-500 font-mono">{c.citation}</span>}
        <span className="text-xs text-gray-400 ml-auto">Score: {(c.score * 100).toFixed(1)}%</span>
      </div>
      <h3 className="font-semibold text-gray-900 text-sm mb-1">{c.title || `${c.petitioner} vs ${c.respondent}`}</h3>
      {c.bench && <p className="text-xs text-gray-500 mb-2"><span className="font-medium">Bench:</span> {c.bench}</p>}
      <div
        className={`text-sm text-gray-600 leading-relaxed ${!expanded ? "line-clamp-3" : ""}`}
        dangerouslySetInnerHTML={{ __html: highlight(c.chunk_text) }}
      />
      <div className="flex items-center gap-3 mt-3">
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-orange-600 hover:text-orange-700 font-medium">
          {expanded ? "Show less" : "Read more"}
        </button>
        {c.pdf_url && (
          <a href={`${API}/cases/${c.case_id}/pdf`} target="_blank" rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1">
            <ExternalLink size={11} /> View PDF
          </a>
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [yearFilter, setYearFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generateAnswer, setGenerateAnswer] = useState(false);
  const [availableYears, setAvailableYears] = useState<number[]>([]);

  useEffect(() => {
    fetch(`${API}/filters/years`).then(r => r.json()).then(setAvailableYears).catch(() => {});
  }, []);

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setLoading(true); setError(null); setResponse(null);
    try {
      const res = await fetch(`${API}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), year: yearFilter ? parseInt(yearFilter) : undefined, generate_answer: generateAnswer }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setResponse(await res.json());
    } catch (err: any) {
      setError(err.message || "Search failed. Is the backend running?");
    } finally { setLoading(false); }
  };

  const examples = ["Right to privacy fundamental right", "Basic structure doctrine", "Bail conditions criminal cases", "Article 370 abrogation", "Land acquisition compensation"];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-2">
          <Scale className="text-orange-500" size={22} />
          <span className="font-bold text-gray-900 text-lg">India Court Search</span>
          <span className="text-xs text-gray-400 ml-1 hidden sm:block">Supreme Court · 1950–2025 · AI-Powered</span>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Search Supreme Court Judgments</h1>
          <p className="text-gray-500 text-sm">100,000+ judgments · Semantic AI search · Instant answers</p>
        </div>
        <form onSubmit={handleSearch} className="mb-6">
          <div className="flex gap-2 mb-3">
            <div className="relative flex-1">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input type="text" value={query} onChange={e => setQuery(e.target.value)}
                placeholder="Search by legal principle, party name, statute…"
                className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-300 bg-white shadow-sm" />
              {query && <button type="button" onClick={() => { setQuery(""); setResponse(null); }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"><X size={16} /></button>}
            </div>
            <button type="submit" disabled={loading || !query.trim()}
              className="bg-orange-500 text-white px-6 py-3 rounded-xl font-medium hover:bg-orange-600 disabled:opacity-50 transition-colors shadow-sm flex items-center gap-2">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />} Search
            </button>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <select value={yearFilter} onChange={e => setYearFilter(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-orange-300">
              <option value="">All years</option>
              {availableYears.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
            <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer ml-auto">
              <input type="checkbox" checked={generateAnswer} onChange={e => setGenerateAnswer(e.target.checked)} className="rounded" />
              <Sparkles size={13} className="text-orange-400" /> Generate AI answer
            </label>
          </div>
        </form>
        {!response && !loading && (
          <div className="mb-8">
            <p className="text-xs text-gray-400 mb-2">Try searching for:</p>
            <div className="flex flex-wrap gap-2">
              {examples.map(q => (
                <button key={q} onClick={() => setQuery(q)}
                  className="text-xs bg-white border border-gray-200 text-gray-600 px-3 py-1.5 rounded-full hover:border-orange-300 hover:text-orange-600 transition-colors">{q}</button>
              ))}
            </div>
          </div>
        )}
        {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm mb-6">{error}</div>}
        {response && (
          <div>
            <p className="text-sm text-gray-500 mb-4">
              <span className="font-medium text-gray-900">{response.total_results}</span> results · {response.latency_ms}ms
            </p>
            {response.answer && (
              <div className="bg-orange-50 border border-orange-200 rounded-xl p-5 mb-5">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles size={14} className="text-orange-500" />
                  <span className="text-sm font-semibold text-orange-800">AI Answer</span>
                </div>
                <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{response.answer}</p>
              </div>
            )}
            <div className="space-y-3">
              {response.results.map(c => <CaseCard key={c.case_id} c={c} query={query} />)}
            </div>
            {response.results.length === 0 && (
              <div className="text-center py-12 text-gray-400">
                <Scale size={40} className="mx-auto mb-3 text-gray-200" />
                <p>No judgments found. Try a different search term.</p>
              </div>
            )}
          </div>
        )}
        {!response && !loading && !error && (
          <div className="text-center py-16 text-gray-300">
            <Scale size={60} className="mx-auto mb-4" />
            <p className="text-gray-400 text-sm">Search across 100,000+ Supreme Court judgments</p>
          </div>
        )}
      </main>
    </div>
  );
}
