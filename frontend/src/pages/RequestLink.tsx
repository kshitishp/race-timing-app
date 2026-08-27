import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { loadVolunteerSession } from "../auth/session";

/** Entry screen for a volunteer who doesn't have (or lost) their magic
 * link — requests a fresh one by email (requirement: resend/self-serve
 * login for volunteers). */
export function RequestLink() {
  const [email, setEmail] = useState("");
  const [raceId, setRaceId] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  if (loadVolunteerSession()) {
    return <Navigate to="/scan" replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("sending");
    setMessage(null);
    try {
      const response = await api.requestMagicLink(email, "volunteer_login", raceId ? Number(raceId) : undefined);
      setStatus("sent");
      setMessage(`Login link sent to ${email}. Check your email (or ask your organiser to forward it).`);
      if (import.meta.env.DEV) {
        console.info("Dev-only magic link URL:", response.magic_link_url);
      }
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiError && err.body && typeof err.body === "object" && "detail" in err.body) {
        setMessage(String((err.body as { detail: string }).detail));
      } else {
        setMessage("Couldn't request a login link. Try again.");
      }
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h1>Race Timing</h1>
        <p>Request your checkpoint login link.</p>
        <form onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <label htmlFor="race-id">Race ID (from your invite, optional)</label>
          <input
            id="race-id"
            inputMode="numeric"
            value={raceId}
            onChange={(e) => setRaceId(e.target.value)}
            placeholder="e.g. 4"
          />
          <button type="submit" disabled={status === "sending"}>
            {status === "sending" ? "Sending…" : "Send login link"}
          </button>
        </form>
        {message && <p className={status === "error" ? "error-text" : "success-text"}>{message}</p>}
      </div>
    </div>
  );
}
