import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch(API + "/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Login failed");
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
      router.push("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{minHeight:"100vh",background:"#f9fafb",display:"flex",alignItems:"center",justifyContent:"center",padding:"1rem"}}>
      <div style={{width:"100%",maxWidth:"400px"}}>
        <div style={{textAlign:"center",marginBottom:"2rem"}}>
          <Link href="/" style={{fontSize:"1.5rem",fontWeight:"bold",color:"#111",textDecoration:"none"}}>
            BharatLawFinder
          </Link>
          <p style={{color:"#6b7280",marginTop:"0.5rem"}}>Sign in to your account</p>
        </div>
        <div style={{background:"white",borderRadius:"1rem",border:"1px solid #e5e7eb",padding:"2rem"}}>
          {error && <div style={{background:"#fef2f2",color:"#dc2626",borderRadius:"0.5rem",padding:"0.75rem",marginBottom:"1rem",fontSize:"0.875rem"}}>{error}</div>}
          <form onSubmit={handleLogin}>
            <div style={{marginBottom:"1rem"}}>
              <label style={{display:"block",fontSize:"0.875rem",fontWeight:"500",marginBottom:"0.25rem"}}>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com"
                style={{width:"100%",border:"1px solid #d1d5db",borderRadius:"0.5rem",padding:"0.625rem 0.75rem",fontSize:"0.875rem",boxSizing:"border-box"}} />
            </div>
            <div style={{marginBottom:"1.5rem"}}>
              <label style={{display:"block",fontSize:"0.875rem",fontWeight:"500",marginBottom:"0.25rem"}}>Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••"
                style={{width:"100%",border:"1px solid #d1d5db",borderRadius:"0.5rem",padding:"0.625rem 0.75rem",fontSize:"0.875rem",boxSizing:"border-box"}} />
            </div>
            <button type="submit" disabled={loading}
              style={{width:"100%",background:"#f97316",color:"white",border:"none",borderRadius:"0.5rem",padding:"0.625rem",fontSize:"0.875rem",fontWeight:"500",cursor:"pointer"}}>
              {loading ? "Loading..." : "Sign In"}
            </button>
          </form>
          <p style={{textAlign:"center",fontSize:"0.875rem",color:"#6b7280",marginTop:"1.5rem"}}>
            Account nahi hai? <Link href="/auth/register" style={{color:"#f97316",fontWeight:"500"}}>Sign up free</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
