import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { Scale, Users, IndianRupee, Zap, Search } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdminDashboard() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) { router.push("/auth/login"); return; }
    Promise.all([
      fetch(`${API}/admin/dashboard`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()),
      fetch(`${API}/admin/users?limit=20`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()),
    ]).then(([d, u]) => {
      if (d.detail === "Admin access required") { router.push("/"); return; }
      setData(d);
      setUsers(u.users || []);
    }).catch(() => router.push("/"))
      .finally(() => setLoading(false));
  }, []);

  const searchUsers = async () => {
    const token = localStorage.getItem("token");
    const res = await fetch(`${API}/admin/users?search=${search}`, { headers: { Authorization: `Bearer ${token}` } });
    const u = await res.json();
    setUsers(u.users || []);
  };

  const changePlan = async (userId: number, planId: number) => {
    const token = localStorage.getItem("token");
    await fetch(`${API}/admin/users/${userId}/plan`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ plan_id: planId }),
    });
    alert("Plan updated!"); window.location.reload();
  };

  const toggleUser = async (userId: number) => {
    const token = localStorage.getItem("token");
    await fetch(`${API}/admin/users/${userId}/toggle-active`, { method: "PATCH", headers: { Authorization: `Bearer ${token}` } });
    window.location.reload();
  };

  if (loading) return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">Loading…</div>;
  if (!data) return null;

  const stats = data.stats || {};

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Scale className="text-orange-500" size={20} />
            <span className="font-bold text-gray-900">Admin Panel</span>
          </Link>
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">← Back to site</Link>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { icon: Users, label: "Total Users", value: stats.total_users, color: "text-blue-500" },
            { icon: IndianRupee, label: "Monthly Revenue", value: `₹${stats.monthly_revenue_inr?.toFixed(0) || 0}`, color: "text-green-500" },
            { icon: Search, label: "Searches Today", value: stats.searches_today, color: "text-orange-500" },
            { icon: Zap, label: "AI Answers Today", value: stats.ai_answers_today, color: "text-purple-500" },
          ].map(({ icon: Icon, label, value, color }) => (
            <div key={label} className="bg-white rounded-xl border border-gray-200 p-4">
              <Icon size={18} className={`${color} mb-2`} />
              <div className="text-xl font-bold text-gray-900">{value ?? 0}</div>
              <div className="text-xs text-gray-500">{label}</div>
            </div>
          ))}
        </div>

        <div className="grid md:grid-cols-2 gap-5 mb-8">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Users by Plan</h2>
            <div className="space-y-3">
              {(data.plan_breakdown || []).map((p: any) => (
                <div key={p.display_name} className="flex items-center justify-between">
                  <span className="text-sm text-gray-700">{p.display_name}</span>
                  <span className="font-semibold text-gray-900">{p.user_count}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Revenue (last 7 days)</h2>
            {(data.daily_revenue || []).length === 0
              ? <p className="text-sm text-gray-400">Abhi tak koi revenue nahi.</p>
              : (data.daily_revenue || []).map((d: any) => (
                <div key={d.day} className="flex items-center justify-between text-sm py-1">
                  <span className="text-gray-500">{d.day}</span>
                  <span className="font-medium text-gray-900">₹{(d.revenue / 100).toFixed(0)}</span>
                </div>
              ))}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-900">All Users</h2>
            <div className="flex gap-2">
              <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search email…"
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-orange-300" />
              <button onClick={searchUsers} className="text-sm bg-orange-500 text-white px-3 py-1.5 rounded-lg hover:bg-orange-600">Search</button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  {["User", "Plan", "Credits", "Joined", "Actions"].map(h => (
                    <th key={h} className="text-left py-2 text-xs text-gray-500 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2.5">
                      <div className="font-medium text-gray-900">{u.full_name || "—"}</div>
                      <div className="text-xs text-gray-500">{u.email}</div>
                    </td>
                    <td className="py-2.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${u.plan_name === "pro" ? "bg-blue-50 text-blue-700" : u.plan_name === "basic" ? "bg-orange-50 text-orange-700" : "bg-gray-100 text-gray-600"}`}>
                        {u.plan_display}
                      </span>
                    </td>
                    <td className="py-2.5 text-gray-700">{u.credits_used}</td>
                    <td className="py-2.5 text-gray-500 text-xs">{new Date(u.created_at).toLocaleDateString("en-IN")}</td>
                    <td className="py-2.5">
                      <div className="flex gap-2">
                        <select defaultValue="" onChange={e => e.target.value && changePlan(u.id, parseInt(e.target.value))}
                          className="text-xs border border-gray-200 rounded px-2 py-1">
                          <option value="" disabled>Change plan</option>
                          <option value="1">Free</option>
                          <option value="2">Basic</option>
                          <option value="3">Pro</option>
                        </select>
                        <button onClick={() => toggleUser(u.id)}
                          className={`text-xs px-2 py-1 rounded border ${u.is_active ? "border-red-200 text-red-600 hover:bg-red-50" : "border-green-200 text-green-600 hover:bg-green-50"}`}>
                          {u.is_active ? "Ban" : "Unban"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}
