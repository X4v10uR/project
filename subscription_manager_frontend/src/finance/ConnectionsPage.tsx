import { ServiceIcon } from '../ServiceIcon'
import { useState, type FormEvent } from "react";
import { api } from "../api";
import { PlanningLayout } from "../subscriptions/PlanningLayout";
import {
  billingCycles,
  buttonClass,
  currencyAmount as money,
  displayDate,
  ErrorBanner,
  Field,
  inputClass,
  panelClass,
  primaryClass,
  showError,
} from "../subscriptions/shared";
import { endpoint, Reverify, useFinance, useFinancePages } from "./common";
import { ManualMatch, StatementImport } from "./StatementPayments";

type Connection = {
  id: number;
  provider: string;
  label: string;
  last_synced_at: string | null;
  error: string;
  enabled: boolean;
};
type Connections = {
  connections: Connection[];
  plaid_configured: boolean;
  gmail_configured: boolean;
  plaid_environment: string;
};
type Candidate = {
  service: string;
  cost: string;
  currency: string;
  billing_cycle: string;
  start_date: string;
  last_payment_date: string;
  paid_through: string;
  next_payment_date: string;
  occurrences: number;
};
type Payment = {
  id: number;
  merchant: string;
  amount: string;
  currency: string;
  date: string;
  provider: string;
  pending: boolean;
  charge: number | null;
  description: string;
  matches: { id: number; service: string; date: string }[];
};
type Discoveries = { candidates: Candidate[]; payments: Payment[]; next: string | null };
type PlaidHandler = { open: () => void; destroy: () => void };
type PlaidClient = {
  create: (options: {
    token: string;
    onSuccess: (
      token: string,
      metadata: { institution?: { name: string } },
    ) => void;
    onExit: () => void;
  }) => PlaidHandler;
};
declare global {
  interface Window {
    Plaid?: PlaidClient;
  }
}

async function loadPlaid() {
  if (window.Plaid) return;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
    script.onload = () => resolve();
    script.onerror = () =>
      reject(
        new Error("Plaid could not load. Check your connection and try again."),
      );
    document.head.appendChild(script);
  });
}

function CandidateCard({
  candidate,
  reload,
}: {
  candidate: Candidate;
  reload: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const fields = Object.fromEntries(new FormData(event.currentTarget));
      const usesDetectedSchedule =
        fields.billing_cycle === candidate.billing_cycle && fields.start_date === candidate.start_date;
      await api("/api/subscriptions/", {
        method: "POST",
        body: JSON.stringify({
          ...fields,
          paid_through: usesDetectedSchedule ? candidate.paid_through : candidate.last_payment_date,
          category: "Other",
        }),
      });
      reload();
    } catch (e) {
      setError(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className={panelClass}>
      <h3 className="font-bold">
        Possible recurring subscription: {candidate.service}
      </h3>
      <p className="my-3 text-sm text-slate-600">
        Detected across {candidate.occurrences} dates. Last payment on {displayDate(candidate.last_payment_date)}.
        Predicted next payment from this history: <strong>{displayDate(candidate.next_payment_date)}</strong>.
      </p>
      <form onSubmit={add} className="grid gap-3 sm:grid-cols-2">
        <Field label="Detected service">
          <input
            className={inputClass}
            name="service_name"
            defaultValue={candidate.service}
            maxLength={100}
            required
          />
        </Field>
        <Field label="Detected amount">
          <input
            className={inputClass}
            type="number"
            name="cost"
            min="0"
            step="0.01"
            defaultValue={candidate.cost}
            required
          />
        </Field>
        <Field label="Detected currency">
          <input
            className={inputClass}
            name="currency"
            maxLength={3}
            pattern="[A-Za-z]{3}"
            defaultValue={candidate.currency}
            required
          />
        </Field>
        <Field label="Detected billing cycle">
          <select
            className={inputClass}
            name="billing_cycle"
            defaultValue={candidate.billing_cycle}
          >
            {billingCycles.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Billing schedule start date">
          <input
            name="start_date"
            className={inputClass}
            type="date"
            defaultValue={candidate.start_date}
            required
          />
        </Field>
        <button className={`${primaryClass} self-end`} disabled={busy}>
          Add reviewed subscription
        </button>
      </form>
      <ErrorBanner message={error} />
    </article>
  );
}

export function ConnectionsPage() {
  const { data, error, reload } = useFinance<Connections>("connections/");
  const {
    data: discovery,
    error: discoveryError,
    reload: reloadDiscovery, pages, next, loading, loadOlder,
  } = useFinancePages<Discoveries>("discoveries/");
  const [matching, setMatching] = useState<number>();
  const [failure, setFailure] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  function refresh() {
    reload();
    reloadDiscovery();
  }
  async function action(task: () => Promise<void>) {
    setBusy(true);
    setFailure("");
    setNotice("");
    try {
      await task();
      refresh();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  async function bank() {
    setBusy(true);
    setFailure("");
    try {
      const { link_token } = await api<{ link_token: string }>(
        endpoint + "connections/plaid/link/",
        { method: "POST" },
      );
      await loadPlaid();
      if (!window.Plaid) throw new Error("Plaid did not initialize.");
      const handler = window.Plaid.create({
        token: link_token,
        onSuccess: (token, metadata) => {
          void action(async () => {
            await api(endpoint + "connections/plaid/exchange/", {
              method: "POST",
              body: JSON.stringify({
                public_token: token,
                label: metadata.institution?.name ?? "Bank account",
              }),
            });
            setNotice("Bank connected. Sync it to review transactions.");
            handler.destroy();
          });
        },
        onExit: () => {
          setBusy(false);
          handler.destroy();
        },
      });
      handler.open();
    } catch (e) {
      setFailure(showError(e));
      setBusy(false);
    }
  }
  async function gmail() {
    await action(async () => {
      const result = await api<{ url: string }>(
        endpoint + "connections/gmail/start/",
        { method: "POST" },
      );
      window.location.assign(result.url);
    });
  }
  return (
    <PlanningLayout title="Connected accounts & discovery" workspace={false}>
      <ErrorBanner message={error || discoveryError || failure} />
      {notice && (
        <p role="status" className={panelClass}>
          {notice}
        </p>
      )}
      <p className="text-sm text-slate-600">
        Find recurring subscriptions from bank payments and Gmail receipts.
        Review suggestions before adding subscriptions or confirming payments.
        Gmail scans up to 50 new receipt and invoice messages per sync from the
        last 90 days and captures supported attachments.
      </p>
      <StatementImport onImport={refresh} />
      <Reverify />
      <section className={panelClass}>
        <h2 className="font-bold">Connect an account</h2>
        <div className="my-3 flex flex-wrap gap-3">
          <button
            className={primaryClass}
            disabled={busy || !data?.plaid_configured}
            onClick={() => void bank()}
          >
            <ServiceIcon name="Plaid" className="mr-2 size-6" />Connect bank with Plaid
          </button>
          <button
            className={buttonClass}
            disabled={busy || !data?.gmail_configured}
            onClick={() => void gmail()}
          >
            <ServiceIcon name="Gmail" className="mr-2 size-6" />Connect Gmail
          </button>
        </div>
        {data && (
          <p className="text-xs text-slate-500">
            {!data.plaid_configured && "Bank connections need server setup. "}
            {!data.gmail_configured && "Gmail connections need server setup. "}
            {data.plaid_configured &&
              data.plaid_environment === "sandbox" &&
              "Plaid is using its sandbox; connect test institutions only."}
          </p>
        )}
      </section>
      {data?.connections.map((c) => (
        <article key={c.id} className={panelClass}>
          <h2 className="font-bold">
            {c.label} · {c.provider === "statement" ? "CSV" : c.provider === "gmail" ? "Gmail" : "Bank"}
          </h2>
          <p className="my-2 text-sm text-slate-500">
            {c.provider === "statement"
              ? "Statement imports"
              : !c.enabled
              ? "Archived import; reconnect the provider to sync new data."
              : c.last_synced_at
                ? `Last synced ${new Date(c.last_synced_at).toLocaleString()}`
                : "Not synced yet"}
          </p>
          <ErrorBanner message={c.error} />
          <div className="mt-3 flex gap-3">
            {c.provider !== "statement" && <button
              className={buttonClass}
              disabled={busy || !c.enabled}
              onClick={() =>
                void action(async () => {
                  await api(endpoint + `connections/${c.id}/`, {
                    method: "POST",
                  });
                  setNotice("Sync complete. Review the results below.");
                })
              }
            >
              Sync now
            </button>}
            <button
              className={buttonClass}
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    c.provider === "statement" ? "Remove the payments imported into this statement account?" : "Disconnect this account and remove its imported transaction data? Saved subscriptions, receipts and charge history will remain.",
                  )
                )
                  void action(async () => {
                    await api(endpoint + `connections/${c.id}/`, {
                      method: "DELETE",
                    });
                  });
              }}
            >
              {c.provider === "statement" ? "Remove statement account" : "Disconnect"}
            </button>
          </div>
        </article>
      ))}
      <h2 className="text-xl font-bold">Subscription suggestions</h2>
      {discovery && !discovery.candidates.length && (
        <p className={panelClass}>
          No recurring patterns found yet. Suggestions need at least two
          payments on different dates.
        </p>
      )}
      {discovery?.candidates.map((c, i) => (
        <CandidateCard
          candidate={c}
          key={c.service + c.currency + i}
          reload={refresh}
        />
      ))}
      <h2 className="text-xl font-bold">Imported payments & invoices</h2>
      {discovery && !discovery.payments.length && (
        <p className={panelClass}>
          Import a statement or sync a connected account to see payments and invoices.
        </p>
      )}
      {pages.flatMap(page => page.payments).map((p) => (
        <article className={panelClass} key={p.id}>
          <div className="flex flex-wrap justify-between gap-3">
            <div>
              <h3 className="flex items-center gap-2 font-bold"><ServiceIcon name={p.merchant} className="size-7" />{p.merchant}</h3>
              <p className="mt-1 text-sm text-slate-500">
                {displayDate(p.date)} · {p.provider} {p.pending && "· Pending"}{" "}
                {p.charge && "· Matched"}
              </p>
              <p className="mt-1 text-sm">{p.description}</p>
            </div>
            <strong>{money(p.amount, p.currency)}</strong>
          </div>
          <div className="mt-3 flex flex-wrap gap-3">
            {p.matches.map((m) => (
              <button
                key={m.id}
                className={primaryClass}
                disabled={busy}
                onClick={() =>
                  void action(async () => {
                    await api(endpoint + `discoveries/${p.id}/`, {
                      method: "POST",
                      body: JSON.stringify({ action: "match", charge: m.id }),
                    });
                  })
                }
              >
                Confirm payment for {m.service} · {displayDate(m.date)}
              </button>
            ))}
            {!p.pending && !p.charge && matching !== p.id && <button className={buttonClass} disabled={busy} onClick={() => setMatching(p.id)}>Match manually</button>}
            <button
              className={buttonClass}
              disabled={busy}
              onClick={() =>
                void action(async () => {
                  await api(endpoint + `discoveries/${p.id}/`, {
                    method: "POST",
                    body: JSON.stringify({ action: "dismiss" }),
                  });
                })
              }
            >
              Dismiss
            </button>
          </div>
          {matching === p.id && !p.charge && <ManualMatch payment={p} onClose={() => setMatching(undefined)} onMatch={() => {
            setMatching(undefined);
            setNotice("Payment matched.");
            refresh();
          }} />}
        </article>
      ))}
      {next && <button className={buttonClass} disabled={loading} onClick={loadOlder}>Load older payments</button>}
    </PlanningLayout>
  );
}
