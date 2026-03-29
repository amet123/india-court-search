import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Scale, Loader2 } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", phone: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Registration failed");
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2">
            <Scale className="text-orange-500" size={28} />
            <span className="text-xl font-bold text-gray-900">BharatLawFinder</span>
          </Link>
          <p className="text-gray-500 mt-2 text-sm">Free account banao</p>
        </div>
        <div className="bg-white rounded-2xl border border-gray-200 p-8 shadow-sm">
          <form onSubmit={handleRegister} className="space-y-4">
            {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">{error}</div>}
            {[
              { key: "full_name", label: "Full Name", type: "text", placeholder: "Rahul Sharma" },
              { key: "email", label: "Email", type: "email", placeholder: "you@example.com" },
              { key: "phone", label: "Phone (optional)", type: "tel", placeholder: "+91 9876543210" },
              { key: "password", label: "Password", type: "password", placeholder: "Min 8 characters" },
            ].map(({ key, label, type, placeholder }) => (
              <div key={key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                <input type={type} value={(form as any)[key]} placeholder={placeholder}
                  onChange={e => setForm({ ...form, [key]: e.target.value })}
                  required={key !== "phone"}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300" />
              </div>
            ))}
            <button type="submit" disabled={loading}
              className="w-full bg-orange-500 text-white py-2.5 rounded-lg font-medium hover:bg-orange-600 disabled:opacity-50 transition-colors flex items-center justify-center gap-2">
              {loading && <Loader2 size={16} className="animate-spin" />}
              Create Account
            </button>
            <p className="text-xs text-center text-gray-400">Sign up karke aap Terms of Service se agree karte hain</p>
          </form>
          <p className="text-center text-sm text-gray-500 mt-6">
            Already account hai?{" "}
            <Link href="/auth/login" className="text-orange-600 font-medium hover:underline">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
