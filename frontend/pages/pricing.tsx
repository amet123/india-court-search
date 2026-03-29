import { useEffect, useState } from "react";
import { Scale, Check, Zap, Crown, ArrowRight } from "lucide-react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const PLAN_FEATURES: Record<string, string[]> = {
  free:  ["10 searches per day", "Keyword search only", "No AI answers", "No PDF access"],
  basic: ["100 searches per day", "Semantic AI search", "50 AI answers/month (Claude Haiku)", "PDF access"],
  pro:   ["Unlimited searches", "Advanced hybrid search", "500 AI answers/month (Claude Sonnet)", "PDF + Export", "API access"],
};

export default function PricingPage() {
  const [plans, setPlans] = useState<any[]>([]);
  const [paying, setPaying] = useState<number | null>(null);
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    fetch(`${API}/payments/plans`).then(r => r.json()).then(setPlans).catch(() => {});
    const token = localStorage.getItem("token");
    if (token) {
      fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
        .then(r => r.json()).then(setUser).catch(() => {});
    }
  }, []);

  const handleSubscribe = async (plan: any) => {
    if (plan.price_monthly === 0) return;
    const token = localStorage.getItem("token");
    if (!token) { window.location.href = "/auth/login?next=/pricing"; return; }
    setPaying(plan.id);
    try {
      const res = await fetch(`${API}/payments/create-order`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ plan_id: plan.id }),
      });
      const order = await res.json();
      if (!res.ok) throw new Error(order.detail || "Order failed");
      const rzp = new (window as any).Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: "INR",
        name: "BharatLawFinder",
        description: `${plan.display_name} Plan`,
        order_id: order.order_id,
        prefill: { name: order.user_name, email: order.user_email },
        theme: { color: "#f97316" },
        handler: async (response: any) => {
          const verifyRes = await fetch(`${API}/payments/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
              plan_id: plan.id,
            }),
          });
          const result = await verifyRes.json();
          if (result.success) { alert(`✅ ${result.message}`); window.location.href = "/dashboard"; }
          else alert("Payment verification failed.");
        },
        modal: { ondismiss: () => setPaying(null) },
      });
      rzp.open();
    } catch (err: any) {
      alert(err.message || "Payment failed");
      setPaying(null);
    }
  };

  return (
    <>
      <script src="https://checkout.razorpay.com/v1/checkout.js" async />
      <div className="min-h-screen bg-gray-50">
        <header className="bg-white border-b border-gray-200">
          <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2">
              <Scale className="text-orange-500" size={22} />
              <span className="font-bold text-gray-900">BharatLawFinder</span>
            </Link>
            {user ? <Link href="/dashboard" className="text-sm text-orange-600 font-medium">My Account</Link>
                  : <Link href="/auth/login" className="text-sm text-orange-600 font-medium">Login</Link>}
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-4 py-12">
          <div className="text-center mb-10">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Simple Pricing</h1>
            <p className="text-gray-500">Apni zaroorat ke hisaab se plan choose karo</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {plans.map((plan) => {
              const isPopular = plan.name === "basic";
              const isCurrent = user?.plan?.name === plan.name;
              const featureList = PLAN_FEATURES[plan.name] || [];
              return (
                <div key={plan.id} className={`rounded-2xl border-2 overflow-hidden bg-white ${isPopular ? "border-orange-400 shadow-lg" : "border-gray-200"}`}>
                  {isPopular && <div className="bg-orange-500 text-white text-center text-xs font-semibold py-1.5">MOST POPULAR</div>}
                  <div className="p-6">
                    <div className="flex items-center gap-2 mb-4">
                      {plan.name === "pro" ? <Crown size={20} className="text-blue-500" /> : plan.name === "basic" ? <Zap size={20} className="text-orange-500" /> : <Scale size={20} className="text-gray-400" />}
                      <span className="font-semibold text-gray-900">{plan.display_name}</span>
                      {isCurrent && <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full ml-auto">Current</span>}
                    </div>
                    <div className="mb-5">
                      {plan.price_monthly === 0
                        ? <span className="text-3xl font-bold text-gray-900">Free</span>
                        : <><span className="text-3xl font-bold text-gray-900">₹{plan.price_monthly / 100}</span><span className="text-gray-500 text-sm">/month</span></>}
                    </div>
                    <div className="space-y-2.5 mb-6">
                      {featureList.map((f, i) => (
                        <div key={i} className="flex items-start gap-2">
                          <Check size={15} className={`mt-0.5 flex-shrink-0 ${f.startsWith("No ") ? "text-gray-300" : "text-green-500"}`} />
                          <span className={`text-sm ${f.startsWith("No ") ? "text-gray-400" : "text-gray-700"}`}>{f}</span>
                        </div>
                      ))}
                    </div>
                    {plan.price_monthly === 0
                      ? <Link href="/auth/register" className="block text-center w-full py-2.5 rounded-xl border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50">Get Started Free</Link>
                      : isCurrent
                        ? <button disabled className="w-full py-2.5 rounded-xl bg-green-50 text-green-700 text-sm font-medium">Current Plan</button>
                        : <button onClick={() => handleSubscribe(plan)} disabled={paying === plan.id}
                            className={`w-full py-2.5 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50 ${isPopular ? "bg-orange-500 text-white hover:bg-orange-600" : "bg-gray-900 text-white hover:bg-gray-800"}`}>
                            {paying === plan.id ? "Processing…" : <><span>Subscribe</span><ArrowRight size={15} /></>}
                          </button>}
                  </div>
                </div>
              );
            })}
          </div>
        </main>
      </div>
    </>
  );
}
