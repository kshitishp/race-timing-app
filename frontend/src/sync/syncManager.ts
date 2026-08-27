import { api } from "../api/client";
import { markSynced, pendingCount, unsyncedTimings } from "../db/localDb";
import { getDeviceId } from "./device";
import type { VolunteerSession } from "../types";

/**
 * Sync trigger strategy (§7 confirmed decision): Safari/WebKit has never
 * implemented the Web Background Sync API, so we don't depend on it.
 * Instead: an `online` event listener plus a periodic in-foreground
 * timer — identical behavior on Android and iOS, no platform-specific
 * path. The volunteer has the app open while working a checkpoint
 * either way.
 */
const FOREGROUND_SYNC_INTERVAL_MS = 15_000;
const BATCH_SIZE = 50;

type Listener = (pending: number) => void;

let intervalHandle: ReturnType<typeof setInterval> | null = null;
let onlineListenerAttached = false;
let syncing = false;
const listeners = new Set<Listener>();

async function notifyListeners() {
  const count = await pendingCount();
  listeners.forEach((l) => l(count));
}

export async function syncOnce(session: VolunteerSession | null): Promise<void> {
  if (!session || syncing || !navigator.onLine) return;
  syncing = true;
  try {
    const pending = await unsyncedTimings();
    if (pending.length === 0) return;

    const deviceId = getDeviceId();
    for (let i = 0; i < pending.length; i += BATCH_SIZE) {
      const batch = pending.slice(i, i + BATCH_SIZE);
      const response = await api.bulkSyncTimings(
        session.sessionToken,
        deviceId,
        batch.map((t) => ({
          client_event_id: t.client_event_id,
          bib_number: t.bib_number,
          timestamp: t.timestamp,
          mode: t.mode,
          success: t.success,
          notes: t.notes,
        }))
      );
      // The server upserts on client_event_id, so any status other than a
      // hard failure means this device no longer needs to hold the row.
      const acknowledged = response.results
        .filter((r) => r.status === "created" || r.status === "already_synced")
        .map((r) => r.client_event_id);
      await markSynced(acknowledged);
    }
  } catch {
    // Offline mid-batch, or the request failed — leave the queue as-is,
    // the next tick (foreground timer or online event) retries.
  } finally {
    syncing = false;
    await notifyListeners();
  }
}

export function startSyncManager(getSession: () => VolunteerSession | null, onPendingChange: Listener) {
  listeners.add(onPendingChange);
  notifyListeners();

  if (!onlineListenerAttached) {
    window.addEventListener("online", () => void syncOnce(getSession()));
    onlineListenerAttached = true;
  }
  if (!intervalHandle) {
    intervalHandle = setInterval(() => void syncOnce(getSession()), FOREGROUND_SYNC_INTERVAL_MS);
  }
  // Fire immediately so a fresh page load doesn't wait a full interval.
  void syncOnce(getSession());

  return () => {
    listeners.delete(onPendingChange);
  };
}
