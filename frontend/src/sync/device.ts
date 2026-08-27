const DEVICE_ID_KEY = "race-timing:device-id";

/** Stable per-browser-install identifier, attached to synced Timings for
 * audit (§8 Timing.device_id). */
export function getDeviceId(): string {
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}
