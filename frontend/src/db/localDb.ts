import Dexie, { type Table } from "dexie";
import type { QueuedTiming } from "../types";

/**
 * Offline queue (§9): every scan/manual entry is written here first, with
 * zero dependency on connectivity. `client_event_id` is unique so a
 * re-render or double-submit never enqueues the same event twice.
 */
class RaceTimingDb extends Dexie {
  timings!: Table<QueuedTiming, string>;

  constructor() {
    super("race-timing-app");
    // IndexedDB keys can't be booleans, so `synced` isn't indexed here —
    // the local queue per event is small enough that a filter() scan is
    // plenty fast; only `created_at` needs an index (for ordering).
    this.version(1).stores({
      timings: "client_event_id, created_at",
    });
  }
}

export const db = new RaceTimingDb();

export async function enqueueTiming(timing: QueuedTiming) {
  await db.timings.add(timing);
}

export async function pendingCount(): Promise<number> {
  return db.timings.filter((t) => !t.synced).count();
}

export async function unsyncedTimings(): Promise<QueuedTiming[]> {
  return db.timings.filter((t) => !t.synced).sortBy("created_at");
}

export async function markSynced(clientEventIds: string[]) {
  await db.transaction("rw", db.timings, async () => {
    for (const id of clientEventIds) {
      await db.timings.update(id, { synced: true });
    }
  });
}

export async function recentTimings(limit = 25): Promise<QueuedTiming[]> {
  return db.timings.orderBy("created_at").reverse().limit(limit).toArray();
}
