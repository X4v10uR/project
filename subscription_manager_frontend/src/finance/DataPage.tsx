import { useRef, useState, type FormEvent } from "react";
import { api, downloadFile } from "../api";
import { useAuth, type AccountUser } from "../accounts/auth";
import { PlanningLayout } from "../subscriptions/PlanningPages";
import {
  buttonClass,
  ErrorBanner,
  Field,
  inputClass,
  panelClass,
  primaryClass,
  showError,
} from "../subscriptions/shared";
import { endpoint, Reverify } from "./common";

type Preview = {
  preview: Record<string, number>;
  exported_at: string;
  account_email: string;
  notice: string;
};
export function DataPage() {
  const { setUser } = useAuth();
  const selectedFile = useRef<File | null>(null);
  const [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState<(Preview & { file: File }) | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  async function exportBackup() {
    setBusy(true);
    setError("");
    try {
      await downloadFile(endpoint + "backup/export/", "dues-backup.zip", {
        method: "POST",
      });
    } catch (e) {
      setError(showError(e));
    } finally {
      setBusy(false);
    }
  }
  async function restore(event: FormEvent<HTMLFormElement>, commit = false) {
    event.preventDefault();
    if (busy || !file || (commit && (!confirmed || preview?.file !== file))) return;
    const restoringFile = file;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const fields = new FormData();
      fields.set("file", file);
      if (commit) fields.set("confirm", "RESTORE");
      const reply = await api<Preview & { restored?: Record<string, number>; user?: AccountUser }>(
        endpoint + "backup/restore/",
        { method: "POST", body: fields },
      );
      if (selectedFile.current !== restoringFile) return;
      if (reply.restored) {
        if (reply.user) setUser(reply.user);
        setNotice(
          `Restored ${reply.restored.subscriptions ?? 0} subscriptions, ${reply.restored.charges ?? 0} charges, and ${reply.restored.receipts ?? 0} receipts.`,
        );
        setPreview(null);
        setConfirmed(false);
      } else {
        setPreview({ ...reply, file: restoringFile });
        setConfirmed(false);
      }
    } catch (e) {
      if (selectedFile.current === restoringFile) setError(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <PlanningLayout title="Backup & restore" workspace={false}>
      <ErrorBanner message={error} />
      {notice && (
        <p role="status" className={panelClass}>
          {notice}
        </p>
      )}
      <Reverify />
      <section className={panelClass}>
        <h2 className="font-bold">Download a complete finance archive</h2>
        <p className="my-3 text-sm text-slate-600">
          Includes personal subscriptions, teams you own, recorded charges,
          participant shares, repayments, price changes, receipts, cards,
          budgets, notifications, and activity. Login secrets, stored provider
          passwords, integration tokens, and private calendar URLs are excluded.
          Keep the archive private.
        </p>
        <button
          className={buttonClass}
          disabled={busy}
          onClick={() => void exportBackup()}
        >
          Download backup ZIP
        </button>
      </section>
      <form
        className={`${panelClass} grid gap-4`}
        onSubmit={(e) => void restore(e)}
      >
        <h2 className="font-bold">Preview a restore</h2>
        <Field label="DUES backup ZIP">
          <input
            className={inputClass}
            type="file"
            accept=".zip,application/zip"
            required
            disabled={busy && confirmed}
            onChange={(e) => {
              selectedFile.current = e.target.files?.[0] ?? null;
              setFile(selectedFile.current);
              setPreview(null);
              setConfirmed(false);
              setError("");
              setNotice("");
            }}
          />
        </Field>
        <button className={buttonClass} disabled={busy || !file}>
          Preview backup
        </button>
      </form>
      {preview && (
        <form
          className={`${panelClass} grid gap-4`}
          onSubmit={(e) => void restore(e, true)}
        >
          <h2 className="font-bold">Archive from {preview.account_email}</h2>
          <p className="text-sm text-slate-500">
            Exported {new Date(preview.exported_at).toLocaleString()}
          </p>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(preview.preview).map(([key, value]) => (
              <div
                className="flex justify-between gap-2 rounded-lg bg-slate-50 p-2"
                key={key}
              >
                <dt className="capitalize">{key}</dt>
                <dd className="font-bold">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="text-sm text-amber-900">{preview.notice}</p>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={confirmed}
              disabled={busy}
              onChange={(e) => setConfirmed(e.target.checked)}
              required
            />
            I understand this adds new copies and does not merge existing
            subscriptions.
          </label>
          <button className={primaryClass} disabled={busy || !confirmed}>
            Restore as new copies
          </button>
        </form>
      )}
    </PlanningLayout>
  );
}
