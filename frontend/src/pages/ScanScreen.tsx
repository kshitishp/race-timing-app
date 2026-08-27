import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ManualEntryForm } from "../components/ManualEntryForm";
import { PendingCounter } from "../components/PendingCounter";
import { QrScanner } from "../components/QrScanner";
import { clearVolunteerSession, loadVolunteerSession } from "../auth/session";
import { db, enqueueTiming, recentTimings } from "../db/localDb";
import { startSyncManager, syncOnce } from "../sync/syncManager";
import type { QueuedTiming, RosterParticipant, VolunteerSession } from "../types";

type Confirmation = { kind: "matched"; participant: RosterParticipant } | { kind: "unmatched"; bib: string };

const DUPLICATE_HINT_WINDOW_SECONDS = 120;

export function ScanScreen() {
  const navigate = useNavigate();
  const [session, setSession] = useState<VolunteerSession | null>(null);
  const [scanMode, setScanMode] = useState<"camera" | "manual">("camera");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [duplicateHint, setDuplicateHint] = useState<string | null>(null);
  const [recent, setRecent] = useState<QueuedTiming[]>([]);
  const [pending, setPending] = useState(0);
  const [online, setOnline] = useState(navigator.onLine);

  const rosterByQrUuid = useMemo(() => {
    const map = new Map<string, RosterParticipant>();
    session?.roster.forEach((p) => map.set(p.profile_qr_uuid, p));
    return map;
  }, [session]);

  const rosterByBib = useMemo(() => {
    const map = new Map<string, RosterParticipant>();
    session?.roster.forEach((p) => map.set(p.bib_number, p));
    return map;
  }, [session]);

  useEffect(() => {
    const loaded = loadVolunteerSession();
    if (!loaded) {
      navigate("/auth/consume");
      return;
    }
    setSession(loaded);
  }, [navigate]);

  useEffect(() => {
    if (!session) return;
    const stop = startSyncManager(() => session, setPending);
    return stop;
  }, [session]);

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  async function refreshRecent() {
    setRecent(await recentTimings(15));
  }

  useEffect(() => {
    void refreshRecent();
  }, [session]);

  async function logTiming(bibNumber: string, matched: RosterParticipant | undefined, mode: "qr" | "manual") {
    const now = new Date();
    const clientEventId = crypto.randomUUID();

    const windowMs = DUPLICATE_HINT_WINDOW_SECONDS * 1000;
    const priorScan = await db.timings
      .filter((t) => t.bib_number === bibNumber && Date.now() - new Date(t.created_at).getTime() < windowMs)
      .first();

    await enqueueTiming({
      client_event_id: clientEventId,
      bib_number: bibNumber,
      timestamp: now.toISOString(),
      mode,
      success: Boolean(matched),
      notes: "",
      synced: false,
      matched_name: matched?.full_name,
      created_at: now.toISOString(),
    });

    setConfirmation(
      matched ? { kind: "matched", participant: matched } : { kind: "unmatched", bib: bibNumber }
    );
    setDuplicateHint(
      priorScan ? `Possible duplicate — bib ${bibNumber} was already logged at this checkpoint recently.` : null
    );

    await refreshRecent();
    void syncOnce(session);

    window.setTimeout(() => setConfirmation(null), 2500);
  }

  function handleDecode(text: string) {
    const matched = rosterByQrUuid.get(text.trim());
    // The QR encodes only the Profile's qr_code_uuid (§8) — if it doesn't
    // resolve against the cached roster, log it anyway rather than
    // silently dropping the scan (§9 point 1); use the raw payload as the
    // "bib" so it's still visible/correctable in results review.
    void logTiming(matched ? matched.bib_number : text.trim(), matched, "qr");
  }

  function handleManualEntry(bib: string) {
    const matched = rosterByBib.get(bib);
    void logTiming(bib, matched, "manual");
  }

  function handleLogout() {
    clearVolunteerSession();
    navigate("/auth/consume");
  }

  if (!session) return null;

  return (
    <div className="scan-screen">
      <header className="scan-header">
        <div>
          <h1>{session.checkpoint.name}</h1>
          <p className="scan-subtitle">{session.race.name}</p>
        </div>
        <button className="link-button" onClick={handleLogout}>
          Log out
        </button>
      </header>

      <PendingCounter pending={pending} online={online} />

      {confirmation && (
        <div className={`confirmation ${confirmation.kind === "unmatched" ? "confirmation--warn" : ""}`}>
          {confirmation.kind === "matched" ? (
            <>
              ✓ {confirmation.participant.full_name} — Bib #{confirmation.participant.bib_number}
            </>
          ) : (
            <>⚠ Unrecognized code/bib "{confirmation.bib}" — logged for review</>
          )}
        </div>
      )}
      {duplicateHint && <div className="duplicate-hint">{duplicateHint}</div>}

      <div className="mode-toggle">
        <button className={scanMode === "camera" ? "active" : ""} onClick={() => setScanMode("camera")}>
          Camera scan
        </button>
        <button className={scanMode === "manual" ? "active" : ""} onClick={() => setScanMode("manual")}>
          Manual entry
        </button>
      </div>

      {scanMode === "camera" ? (
        <QrScanner active={scanMode === "camera"} onDecode={handleDecode} />
      ) : (
        <ManualEntryForm onSubmit={handleManualEntry} />
      )}

      <section className="recent-list">
        <h2>Recent at this checkpoint</h2>
        <ul>
          {recent.map((t) => (
            <li key={t.client_event_id}>
              <span>{t.matched_name ?? `Bib ${t.bib_number}`}</span>
              <span>{new Date(t.timestamp).toLocaleTimeString()}</span>
              <span className={t.synced ? "badge badge--synced" : "badge badge--pending"}>
                {t.synced ? "synced" : "pending"}
              </span>
            </li>
          ))}
          {recent.length === 0 && <li className="empty">No scans yet.</li>}
        </ul>
      </section>
    </div>
  );
}
