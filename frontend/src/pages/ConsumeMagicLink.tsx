import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { saveVolunteerSession } from "../auth/session";
import type { ConsumeMagicLinkResponse } from "../types";

type Status = "consuming" | "error" | "organiser" | "done";

export function ConsumeMagicLink() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status>("consuming");
  const [error, setError] = useState<string | null>(null);
  const token = searchParams.get("token");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setError("This link is missing its token.");
      return;
    }

    api
      .consumeMagicLink(token)
      .then((response) => {
        const data = response as ConsumeMagicLinkResponse;
        if (data.purpose === "volunteer_login" && data.race && data.checkpoint) {
          saveVolunteerSession(data);
          setStatus("done");
          navigate("/scan", { replace: true });
        } else {
          // Organiser login: race/checkpoint setup happens in Django
          // Admin (§6 confirmed decision) — this PWA is the volunteer
          // scan surface. Nothing further to do here.
          setStatus("organiser");
        }
      })
      .catch((err) => {
        setStatus("error");
        if (err instanceof ApiError && err.body && typeof err.body === "object" && "detail" in err.body) {
          setError(String((err.body as { detail: string }).detail));
        } else {
          setError("Something went wrong consuming this link.");
        }
      });
  }, [token, navigate]);

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h1>Race Timing</h1>
        {status === "consuming" && <p>Signing you in…</p>}
        {status === "error" && (
          <>
            <p className="error-text">{error}</p>
            <p>Ask your race organiser to resend your checkpoint link.</p>
          </>
        )}
        {status === "organiser" && (
          <p>
            You're signed in as an organiser. Race, checkpoint, and participant setup happens in the admin
            dashboard your organiser account has access to.
          </p>
        )}
      </div>
    </div>
  );
}
