import { useState, type FormEvent } from "react";

interface Props {
  onSubmit: (bibNumber: string) => void;
}

export function ManualEntryForm({ onSubmit }: Props) {
  const [bib, setBib] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = bib.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setBib("");
  }

  return (
    <form className="manual-entry" onSubmit={handleSubmit}>
      <label htmlFor="bib-input">Manual entry (bib number)</label>
      <div className="manual-entry-row">
        <input
          id="bib-input"
          inputMode="numeric"
          autoComplete="off"
          placeholder="e.g. 142"
          value={bib}
          onChange={(e) => setBib(e.target.value)}
        />
        <button type="submit">Log time</button>
      </div>
    </form>
  );
}
