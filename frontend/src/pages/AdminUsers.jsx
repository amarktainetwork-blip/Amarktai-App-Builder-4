import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, UserPlus } from "lucide-react";
import { toast } from "sonner";
import Header from "@/components/Header";
import { Button } from "@/components/ui/button";
import { Admin } from "@/lib/amk-api";

export default function AdminUsersPage() {
  const nav = useNavigate();
  const [users, setUsers] = useState([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");

  const refresh = () => Admin.users().then(setUsers).catch(() => toast.error("Admin access required"));
  useEffect(() => { refresh(); }, []);

  const create = async (e) => {
    e.preventDefault();
    try {
      await Admin.createUser({ email, password, role });
      setEmail("");
      setPassword("");
      setRole("user");
      toast.success("User created.");
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create user");
    }
  };

  const reset = async (id) => {
    const next = window.prompt("New password, at least 12 characters");
    if (!next) return;
    try {
      await Admin.resetPassword(id, next);
      toast.success("Password reset.");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Reset failed");
    }
  };

  const setStatus = async (id, status) => {
    try {
      await Admin.setStatus(id, status);
      refresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Status update failed");
    }
  };

  return (
    <div className="min-h-screen bg-amk-base">
      <Header rightExtra={
        <button onClick={() => nav("/app")} className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white">
          <ArrowLeft className="w-3 h-3" /> dashboard
        </button>
      } />
      <main className="max-w-5xl mx-auto p-6 grid lg:grid-cols-[340px,1fr] gap-5">
        <form onSubmit={create} className="border border-amk-line bg-amk-panel p-4 h-fit">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">[ create user ]</div>
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email"
            className="w-full bg-amk-base border border-amk-line h-10 px-3 font-mono text-sm mb-3" />
          <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="temporary password"
            type="password" className="w-full bg-amk-base border border-amk-line h-10 px-3 font-mono text-sm mb-3" />
          <select value={role} onChange={(e) => setRole(e.target.value)}
            className="w-full bg-amk-base border border-amk-line h-10 px-3 font-mono text-sm mb-3">
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
          <Button className="w-full bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs">
            <UserPlus className="w-3.5 h-3.5 mr-1.5" /> Create
          </Button>
        </form>
        <section className="border border-amk-line bg-amk-panel">
          {users.map((u) => (
            <div key={u.id} className="grid md:grid-cols-[1fr,90px,100px,210px] gap-3 border-b border-amk-line last:border-b-0 p-3 items-center">
              <div>
                <div className="font-mono text-sm text-white">{u.email}</div>
                <div className="font-mono text-[10px] text-amk-fg3">{u.id}</div>
              </div>
              <div className="font-mono text-xs text-amk-fg2">{u.role}</div>
              <div className={`font-mono text-xs ${u.status === "active" ? "text-agent-coder" : "text-agent-scout"}`}>{u.status}</div>
              <div className="flex gap-2 justify-end">
                <Button variant="ghost" size="sm" onClick={() => reset(u.id)} className="border border-amk-line font-mono text-xs">Reset</Button>
                <Button variant="ghost" size="sm" onClick={() => setStatus(u.id, u.status === "active" ? "disabled" : "active")} className="border border-amk-line font-mono text-xs">
                  {u.status === "active" ? "Disable" : "Enable"}
                </Button>
              </div>
            </div>
          ))}
        </section>
      </main>
    </div>
  );
}
