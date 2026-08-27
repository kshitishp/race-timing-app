interface Props {
  pending: number;
  online: boolean;
}

/** Live count of scans not yet synced (§9 user story: "so I trust
 * nothing is being lost"). */
export function PendingCounter({ pending, online }: Props) {
  return (
    <div className={`pending-counter ${pending > 0 ? "pending-counter--active" : ""}`}>
      <span className={`status-dot ${online ? "status-dot--online" : "status-dot--offline"}`} />
      <span>{online ? "Online" : "Offline"}</span>
      <span className="pending-counter-sep">·</span>
      <span>{pending} pending sync</span>
    </div>
  );
}
