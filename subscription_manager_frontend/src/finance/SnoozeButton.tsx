import { useState } from "react";
import { api } from "../api";
import { ErrorBanner, showError } from "../subscriptions/shared";
import { endpoint } from "./common";

export function SnoozeButton({
  id,
  onSnooze,
}: {
  id: number;
  onSnooze?: () => void;
}) {
  const [notice, setNotice] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function snooze() {
    setBusy(true);
    setError("");
    try {
      await api(endpoint + `notifications/${id}/snooze/`, {
        method: "POST",
        body: JSON.stringify({ hours: 24 }),
      });
      setNotice("Reminder set for tomorrow.");
      onSnooze?.();
    } catch (e) {
      setError(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="hover:underline disabled:opacity-50"
        type="button"
        disabled={busy || !!notice}
        onClick={() => void snooze()}
      >
        Remind me tomorrow
      </button>
      {notice && <span role="status">{notice}</span>}
      <ErrorBanner message={error} />
    </>
  );
}
