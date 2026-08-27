import type { ConsumeMagicLinkResponse, VolunteerSession } from "../types";

const STORAGE_KEY = "race-timing:volunteer-session";

/**
 * Cached on volunteer login while online (§9): checkpoint, race roster
 * (bib/name/QR uuid), and a long-lived signed session token so the
 * device stays "logged in" without connectivity. Session-token expiry is
 * checked client-side (it's a JWT); revocation is only checked the next
 * time the device is online and hits the API.
 */
export function saveVolunteerSession(response: ConsumeMagicLinkResponse): VolunteerSession {
  if (!response.race || !response.checkpoint || !response.roster) {
    throw new Error("Not a volunteer session response.");
  }
  const session: VolunteerSession = {
    sessionToken: response.session_token,
    user: response.user,
    race: response.race,
    checkpoint: response.checkpoint,
    roster: response.roster,
    cachedAt: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return session;
}

export function loadVolunteerSession(): VolunteerSession | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as VolunteerSession;
  } catch {
    return null;
  }
}

export function clearVolunteerSession() {
  localStorage.removeItem(STORAGE_KEY);
}

/** Client-side-only expiry check on the JWT (no network needed). */
export function isSessionTokenExpired(token: string): boolean {
  try {
    const [, payloadB64] = token.split(".");
    const payload = JSON.parse(atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/")));
    if (!payload.exp) return false;
    return Date.now() >= payload.exp * 1000;
  } catch {
    return true;
  }
}
