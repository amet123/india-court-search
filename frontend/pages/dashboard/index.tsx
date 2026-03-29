import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { Scale, Zap, Crown, LogOut, CreditCard, Search } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [subs, setSubs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.push("/auth/login"); return; }
    Promise.all([
      fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()),
      fetch(`${API}/payments/my-subscriptions`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()),
    ]).then(([u, s]) => {
      setUser(u);
      setSubs(Array.isArray(s) ? s : []);
    }).catch(() => router.push("/auth/login"))
      .finally(() => setLoading(false));
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    router.push("/");
  };

  const handleCancelSub = async () => {
    if (!confirm("Subscription cancel karna chahte ho? Free plan pe aa jaoge.")) return;
    const token = localStorage.getItem("token");
    await fetch(`${API}/payments/cancel`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    window.location.reload();
  };

  if (loading) return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">Loading…</div>;
  if (!user) return null;

  const plan = user.plan || {};
  const creditsPercent = plan.credits_monthly > 0 ? Math.min(100, Math.round((plan.credits_used / plan.credits_monthly) * 100)) : 0;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Scale className="text-orange-500" size={20} />
            <span className="font-bold text-gray-900">BharatLawFinder</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600 hidden sm:block">{user.email}</span>
            <button onClick={handleLogout} className="text-gray-400 hover:text-gray-600"><LogOut size={18} /></button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">My Account</h1>

        <div className="grid md:grid-cols-3 gap-5 mb-8">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-3">
              {plan.name === "pro" ? <Crown size={18} className="text-blue-500" /> : plan.name === "basic" ? <Zap size={18} className="text-orange-500" /> : <Scale size={18} className="text-gray-400" />}
              <span className="font-semibold text-gray-900">{plan.display || "Free"} Plan</span>
            </div>
            {plan.expires_at && <p className="text-xs text-gray-500 mb-3">Renews: {new Date(plan.expires_at).toLocaleDateString("en-IN")}</p>}
            {plan.name === "free"
              ? <Link href="/pricing" className="block text-center w-full py-2 rounded-lg bg-orange-500 text-white text-sm font-medium hover:bg-orange-600 transition-colors">Upgrade Plan</Link>
              : <button onClick={handleCancelSub} className="w-full py-2 rounded-lg border border-gray-200 text-gray-600 text-sm hover:bg-gray-50 transition-colors">Cancel Subscription</button>}
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-3">
              <Zap size={18} className="text-orange-400" />
              <span className="font-semibold text-gray-900">AI Credits</span>
            </div>
            {plan.credits_monthly > 0 ? (
              <>
                <div className="flex justify-between text-xs text-gray-500 mb-2">
                  <span>{plan.credits_used} used</span>
                  <span>{plan.credits_remaining} remaining</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full transition-all ${creditsPercent > 80 ? "bg-red-400" : "bg-orange-400"}`} style={{ width: `${creditsPercent}%` }} />
                </div>
                <p className="text-xs text-gray-400 mt-2">{plan.credits_monthly} credits/month · 1st ko reset</p>
              </>
            ) : (
              <p className="text-sm text-gray-400">Free plan pe AI credits nahi hain. <Link href="/pricing" className="text-orange-600 underline">Upgrade karo</Link></p>
            )}
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-3">
              <Search size={18} className="text-blue-400" />
              <span className="font-semibold text-gray-900">Daily Searches</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{plan.searches_daily === -1 ? "∞" : plan.searches_daily}</p>
            <p className="text-xs text-gray-400 mt-1">{plan.searches_daily === -1 ? "Unlimited searches" : "searches per day"}</p>
            <p className="text-xs text-gray-400 mt-1">Model: <span className="font-medium text-gray-700">{plan.llm_model === "none" ? "Not included" : plan.llm_model}</span></p>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <CreditCard size={16} /> Payment History
          </h2>
          {subs.length === 0 ? (
            <p className="text-sm text-gray-400">Abhi tak koi payment nahi.</p>
          ) : (
            <div className="space-y-2">
              {subs.map((s) => (
                <div key={s.id} className="flex items-center justify-between text-sm py-2 border-b border-gray-50 last:border-0">
                  <div>
                    <span className="font-medium text-gray-800">{s.plan_display}</span>
                    <span className="text-gray-400 ml-2 text-xs">{new Date(s.created_at).toLocaleDateString("en-IN")}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    {s.amount_paid && <span className="text-gray-700 font-medium">₹{s.amount_paid / 100}</span>}
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.status === "active" ? "bg-green-50 text-green-700" : s.status === "cancelled" ? "bg-red-50 text-red-700" : "bg-gray-100 text-gray-600"}`}>
                      {s.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-6 text-center">
          <Link href="/" className="text-sm text-orange-600 hover:underline">← Back to Search</Link>
        </div>
      </main>
    </div>
  );
}
