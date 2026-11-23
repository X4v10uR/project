import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import {
  buttonClass,
  ErrorBanner,
  Field,
  inputClass,
  panelClass,
  showError,
} from "../subscriptions/shared";

export const endpoint = "/api/finance/";
export function useFinance<T>(path: string) {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<{ path: string; version: number; data?: T; error?: string }>();
  useEffect(() => {
    const controller = new AbortController();
    api<T>(endpoint + path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ path, version, data });
      })
      .catch((e) => {
        if (!controller.signal.aborted) setResult({ path, version, error: showError(e) });
      });
    return () => controller.abort();
  }, [path, version]);
  const current = result?.path === path && result.version === version ? result : undefined;
  return { data: current?.data ?? null, error: current?.error ?? "", reload: () => setVersion((v) => v + 1) };
}

export function useFinancePages<T extends { next: string | null }>(path: string) {
  const { data, error, reload } = useFinance<T>(path);
  const [tail, setTail] = useState<{ first: T; pages: T[]; loading: boolean; error: string }>();
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => { pending.current?.abort(); pending.current = null; }, [data]);
  const current = data && tail?.first === data ? tail : undefined;
  const pages = data ? [data, ...(current?.pages ?? [])] : [];
  const next = pages.at(-1)?.next;
  async function loadOlder() {
    if (!next || !data || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    const previous = current?.pages ?? [];
    setTail({ first: data, pages: previous, loading: true, error: "" });
    try {
      // Keep session requests on this origin when the API is behind a proxy.
      const query = new URL(next, window.location.origin).search;
      const page = await api<T>(endpoint + path.split("?")[0] + query, { signal: controller.signal });
      if (!controller.signal.aborted) setTail({ first: data, pages: [...previous, page], loading: false, error: "" });
    } catch (failure) {
      if (!controller.signal.aborted) setTail({ first: data, pages: previous, loading: false, error: showError(failure) });
    } finally {
      if (pending.current === controller) pending.current = null;
    }
  }
  return { pages, data, error: error || current?.error || "", reload, next, loading: current?.loading, loadOlder };
}

export function Reverify() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const form = event.currentTarget;
    try {
      await api("/api/accounts/security/", {
        method: "POST",
        body: JSON.stringify({
          action: "reauthenticate",
          ...Object.fromEntries(new FormData(form)),
        }),
      });
      form.reset();
      setNotice("Verified for five minutes.");
    } catch (e) {
      setError(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className={panelClass}>
      <summary className="cursor-pointer font-bold">
        Verify password for sensitive actions
      </summary>
      <p className="my-3 text-sm text-slate-600">
        Required when connecting accounts, disconnecting providers, or
        transferring a backup.
      </p>
      <form onSubmit={verify} className="grid gap-3 sm:grid-cols-2">
        <Field label="Current DUES password">
          <input
            className={inputClass}
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
        </Field>
        <Field label="Authenticator or recovery code (if enabled)">
          <input
            name="otp"
            className={inputClass}
            autoComplete="one-time-code"
          />
        </Field>
        <button className={buttonClass} disabled={busy}>
          Verify password
        </button>
      </form>
      <ErrorBanner message={error} />
      {notice && (
        <p role="status" className="mt-3 text-sm">
          {notice}
        </p>
      )}
    </details>
  );
}

type Converted = {
  base: string;
  monthly_total: string;
  complete: boolean;
  missing: string[];
  error: string;
  rates: {
    quote: string;
    rate: string;
    as_of: string;
    source: string;
    stale: boolean;
  }[];
};
export function CurrencySummary() {
  const [params] = useSearchParams(),
    [base, setBase] = useState(""),
    [busy, setBusy] = useState(false),
    [failure, setFailure] = useState("");
  const [updated, setUpdated] = useState<Converted | null>(null);
  const path = `conversion/?scope=${params.get("scope") === "teams" ? "teams" : "personal"}${base ? "&base=" + encodeURIComponent(base) : ""}`;
  const { data, error } = useFinance<Converted>(path);
  useEffect(() => setUpdated(null), [path]);
  const value = updated ?? data;
  async function refresh() {
    setBusy(true);
    setFailure("");
    try {
      setUpdated(await api<Converted>(endpoint + path, { method: "POST" }));
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className={panelClass}>
      <h2 className="text-lg font-bold">Combined monthly spending</h2>
      <p className="mt-2 text-sm text-slate-600">
        Convert commitments using saved reference rates. Original amounts stay
        in their own currencies.
      </p>
      <div className="my-4 flex flex-wrap items-end gap-3">
        <Field label="Display currency">
          <input
            className={inputClass}
            value={base}
            onChange={(e) => {
              setBase(e.target.value.toUpperCase());
              setUpdated(null);
            }}
            maxLength={3}
            placeholder={value?.base ?? "Preferred currency"}
          />
        </Field>
        <button
          className={buttonClass}
          onClick={() => void refresh()}
          disabled={busy || (base.length > 0 && base.length !== 3)}
        >
          {busy ? "Refreshing…" : "Refresh exchange rates"}
        </button>
      </div>
      <ErrorBanner message={error || failure || value?.error || ""} />
      {value && (
        <>
          <strong className="text-2xl">
            {value.base} {value.monthly_total}
            {!value.complete && " (partial)"}
          </strong>
          {value.missing.length > 0 && (
            <p className="mt-2 text-sm text-amber-800">
              Missing rates for {value.missing.join(", ")}. Refresh rates to
              include them.
            </p>
          )}
          <ul className="mt-3 text-xs text-slate-500">
            {value.rates.map((r) => (
              <li key={r.quote}>
                1 {value.base} = {r.rate} {r.quote} · {r.source}, {r.as_of}
                {r.stale && " · Older than seven days"}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

type Feed = { id: number; scope: string; created_at: string };
export function LiveCalendar() {
  const { data, error, reload } = useFinance<{ feeds: Feed[] }>(
    "calendar/feeds/",
  );
  const [params] = useSearchParams(),
    [url, setUrl] = useState(""),
    [failure, setFailure] = useState(""),
    [busy, setBusy] = useState(false);
  async function create() {
    setBusy(true);
    setFailure("");
    try {
      const reply = await api<{ url: string }>(endpoint + "calendar/feeds/", {
        method: "POST",
        body: JSON.stringify({
          scope: params.get("scope") === "teams" ? "teams" : "personal",
        }),
      });
      setUrl(reply.url);
      reload();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: number) {
    setBusy(true);
    setFailure("");
    try {
      await api(endpoint + "calendar/feeds/", {
        method: "DELETE",
        body: JSON.stringify({ id }),
      });
      setUrl("");
      reload();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className={panelClass}>
      <h2 className="font-bold">Subscribe to a live calendar</h2>
      <p className="my-3 text-sm text-slate-600">
        Add this private URL in Google Calendar, Outlook, or Apple Calendar
        using “Subscribe by URL”. Changes appear when your calendar refreshes.
        Anyone with the URL can read its events; revoke it below to stop access.
      </p>
      <ErrorBanner message={error || failure} />
      <button
        className={buttonClass}
        disabled={busy}
        onClick={() => void create()}
      >
        Create private calendar URL
      </button>
      {url && (
        <Field label="New calendar subscription URL">
          <input
            className={`${inputClass} mt-3`}
            value={url}
            readOnly
            onFocus={(e) => e.currentTarget.select()}
          />
        </Field>
      )}
      <ul className="mt-3 grid gap-2">
        {data?.feeds.map((f) => (
          <li
            key={f.id}
            className="flex items-center justify-between gap-3 text-sm"
          >
            <span className="capitalize">
              {f.scope} · Created {new Date(f.created_at).toLocaleDateString()}
            </span>
            <button
              className={buttonClass}
              disabled={busy}
              onClick={() => void remove(f.id)}
            >
              Revoke
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
