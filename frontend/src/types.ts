export interface UserSummary {
  id: number;
  email: string;
  name: string;
  phone: string | null;
}

export interface RaceSummary {
  id: number;
  name: string;
  slug: string;
  event_date: string;
  start_time: string;
  timezone: string;
  status: string;
}

export interface CheckpointSummary {
  id: number;
  race: number;
  name: string;
  sequence_order: number;
  type: "start" | "checkpoint" | "finish";
}

export interface RosterParticipant {
  id: number;
  bib_number: string;
  full_name: string;
  profile_qr_uuid: string;
  category: string;
  status: string;
}

export interface ConsumeMagicLinkResponse {
  purpose: "organiser_login" | "volunteer_login";
  user: UserSummary;
  race: RaceSummary | null;
  checkpoint: CheckpointSummary | null;
  roster: RosterParticipant[] | null;
  session_token: string;
}

export interface VolunteerSession {
  sessionToken: string;
  user: UserSummary;
  race: RaceSummary;
  checkpoint: CheckpointSummary;
  roster: RosterParticipant[];
  cachedAt: string;
}

/** A scan or manual entry captured on-device, queued locally until sync
 * (§9 Offline-First Sync Design). `client_event_id` is the idempotency
 * key the server upserts on. */
export interface QueuedTiming {
  client_event_id: string;
  bib_number: string;
  timestamp: string;
  mode: "qr" | "manual";
  success: boolean;
  notes: string;
  synced: boolean;
  matched_name?: string;
  created_at: string;
}
