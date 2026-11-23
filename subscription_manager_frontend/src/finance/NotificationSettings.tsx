import { useState, type FormEvent } from "react";
import { api } from "../api";
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
import { endpoint, useFinance } from "./common";

type Preferences = {
  email_enabled: boolean;
  push_enabled: boolean;
  digest: string;
  quiet_start: string | null;
  quiet_end: string | null;
  vapid_public_key: string;
  push_configured: boolean;
  timezone: string;
};
function keyBytes(key: string) {
  const raw = atob(key.replaceAll("-", "+").replaceAll("_", "/"));
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}
export function NotificationSettingsPage() {
  const { data, error, reload } = useFinance<Preferences>(
    "notifications/preferences/",
  );
  const [failure, setFailure] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setFailure("");
    setNotice("");
    try {
      await api(endpoint + "notifications/preferences/", {
        method: "PUT",
        body: JSON.stringify({
          email_enabled: form.has("email_enabled"),
          push_enabled: data?.push_enabled ?? false,
          digest: form.get("digest"),
          quiet_start: form.get("quiet_start") || null,
          quiet_end: form.get("quiet_end") || null,
        }),
      });
      setNotice("Notification preferences saved.");
      reload();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  async function push(enable: boolean) {
    if (!data) return;
    setBusy(true);
    setFailure("");
    setNotice("");
    try {
      if (enable && (
        !("serviceWorker" in navigator) ||
        !("PushManager" in window) ||
        !("Notification" in window)
      ))
        throw new Error("This browser does not support push notifications.");
      if (enable) {
        // Request permission while this click still has user activation.
        if ((await Notification.requestPermission()) !== "granted")
          throw new Error(
            "Notification permission was not granted. Update this site’s browser permissions to try again.",
          );
        await navigator.serviceWorker.register("/notification-worker.js");
        const registration = await navigator.serviceWorker.ready;
        let subscription = await registration.pushManager.getSubscription();
        subscription ??= await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: keyBytes(data.vapid_public_key),
        });
        await api(endpoint + "notifications/push/", {
          method: "POST",
          body: JSON.stringify(subscription.toJSON()),
        });
      } else if ("serviceWorker" in navigator) {
        const registration = await navigator.serviceWorker.getRegistration("/");
        const subscription = await registration?.pushManager?.getSubscription();
        if (subscription) {
          await api(endpoint + "notifications/push/", {
            method: "DELETE",
            body: JSON.stringify({ endpoint: subscription.endpoint }),
          });
          await subscription.unsubscribe();
        }
      }
      await api(endpoint + "notifications/preferences/", {
        method: "PUT",
        body: JSON.stringify({ push_enabled: enable }),
      });
      setNotice(
        enable
          ? "Push notifications enabled on this browser."
          : "Push notifications disabled.",
      );
      reload();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <PlanningLayout title="Notification preferences" workspace={false}>
      <ErrorBanner message={error || failure} />
      {notice && (
        <p role="status" className={panelClass}>
          {notice}
        </p>
      )}
      {data && (
        <>
          <form className={`${panelClass} grid gap-4`} onSubmit={save}>
            <h2 className="font-bold">Email & quiet hours</h2>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                name="email_enabled"
                defaultChecked={data.email_enabled}
              />
              Email alerts enabled
            </label>
            <Field label="Email delivery">
              <select
                className={inputClass}
                name="digest"
                defaultValue={data.digest}
              >
                <option value="off">Individual alerts</option>
                <option value="daily">Daily summary</option>
                <option value="weekly">Weekly summary</option>
              </select>
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Quiet hours start">
                <input
                  className={inputClass}
                  type="time"
                  name="quiet_start"
                  defaultValue={data.quiet_start?.slice(0, 5) ?? ""}
                />
              </Field>
              <Field label="Quiet hours end">
                <input
                  className={inputClass}
                  type="time"
                  name="quiet_end"
                  defaultValue={data.quiet_end?.slice(0, 5) ?? ""}
                />
              </Field>
            </div>
            <p className="text-sm text-slate-600">
              Times use {data.timezone}, set in your profile. Email and push
              wait until quiet hours end; in-app alerts remain available. Daily
              and weekly summaries replace individual alert emails. Summaries
              are sent after 9 AM when the notification job runs.
            </p>
            <button disabled={busy} className={primaryClass}>
              Save notification preferences
            </button>
          </form>
          <section className={panelClass}>
            <h2 className="font-bold">Browser & mobile push</h2>
            <p className="my-3 text-sm text-slate-600">
              Push status: {data.push_enabled ? "Enabled" : "Off"}. Enable each
              browser you use. On mobile, support depends on your browser and
              installation settings.
            </p>
            {!data.push_configured && (
              <p className="mb-3 text-sm text-amber-800">
                Push delivery needs server setup before it can be enabled.
              </p>
            )}
            <div className="flex flex-wrap gap-3">
              <button
                className={buttonClass}
                disabled={busy || !data.push_configured}
                onClick={() => void push(true)}
              >
                Enable on this browser
              </button>
              <button
                className={buttonClass}
                disabled={busy}
                onClick={() => void push(false)}
              >
                Disable push notifications
              </button>
            </div>
          </section>
        </>
      )}
    </PlanningLayout>
  );
}

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
