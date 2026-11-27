import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { PlanningLayout } from "../subscriptions/PlanningLayout";
import {
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
import { endpoint, useFinance, useFinancePages } from "./common";

type Budget = {
  id: number;
  team: string | null;
  team_id: number | null;
  category: string;
  currency: string;
  monthly_limit: string;
  warning_percent: number;
  spend: string;
  percent: string;
};
type Budgets = {
  budgets: Budget[];
  teams: { id: number; name: string }[];
  categories: string[];
};
export function BudgetsPage() {
  const { data, error, reload } = useFinance<Budgets>("budgets/");
  const [failure, setFailure] = useState(""),
    [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = Object.fromEntries(new FormData(form));
    setBusy(true);
    setFailure("");
    try {
      await api(endpoint + "budgets/", {
        method: "POST",
        body: JSON.stringify({
          ...fields,
          team_id: fields.team_id ? Number(fields.team_id) : null,
        }),
      });
      reload();
      form.reset();
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
      await api(endpoint + `budgets/${id}/`, { method: "DELETE" });
      reload();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <PlanningLayout title="Detailed spending budgets" workspace={false}>
      <ErrorBanner message={error || failure} />
      <p className="text-sm text-slate-600">
        Set a monthly commitment limit for a category or a whole workspace.
        Personal limits use your share; individual team limits use the full team
        price. Saving the same workspace, category and currency updates its
        limit.
      </p>
      <form
        className={`${panelClass} grid gap-4 sm:grid-cols-2 lg:grid-cols-3`}
        onSubmit={save}
      >
        <Field label="Budget workspace">
          <select name="team_id" className={inputClass}>
            <option value="">Personal</option>
            {data?.teams.map((t) => (
              <option value={t.id} key={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Budget category">
          <input
            className={inputClass}
            name="category"
            list="budget-categories"
            placeholder="All categories"
            maxLength={50}
          />
          <datalist id="budget-categories">
            {data?.categories.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </Field>
        <Field label="Budget currency">
          <input
            className={inputClass}
            name="currency"
            defaultValue="USD"
            maxLength={3}
            pattern="[A-Za-z]{3}"
            required
          />
        </Field>
        <Field label="Monthly limit">
          <input
            className={inputClass}
            name="monthly_limit"
            type="number"
            min="0.01"
            step="0.01"
            required
          />
        </Field>
        <Field label="Warn at (%)">
          <input
            className={inputClass}
            name="warning_percent"
            type="number"
            min={1}
            max={99}
            defaultValue={80}
            required
          />
        </Field>
        <button className={`${primaryClass} self-end`} disabled={busy}>
          Save detailed budget
        </button>
      </form>
      {data && !data.budgets.length && (
        <p className={panelClass}>
          No detailed budgets yet. Your dashboard limits remain available.
        </p>
      )}
      {data?.budgets.map((b) => (
        <article className={panelClass} key={b.id}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-bold">
                {b.team ?? "Personal"} · {b.category || "All categories"}
              </h2>
              <p className="mt-2 text-sm">
                {money(b.spend, b.currency)} of{" "}
                {money(b.monthly_limit, b.currency)} · {b.percent}% · Warning at{" "}
                {b.warning_percent}%
              </p>
            </div>
            <button
              className={buttonClass}
              disabled={busy}
              onClick={() => void remove(b.id)}
            >
              Remove budget
            </button>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full ${Number(b.percent) >= 100 ? "bg-red-500" : "bg-indigo-500"}`}
              style={{ width: Math.min(100, Number(b.percent)) + "%" }}
            />
          </div>
        </article>
      ))}
    </PlanningLayout>
  );
}

type Receipt = {
  id: number;
  filename: string;
  merchant: string;
  amount: string | null;
  currency: string;
  issued_on: string | null;
  note: string;
  subscription: number | null;
  charge: number | null;
  extraction_status: string;
  download_url: string;
  can_edit: boolean;
};
type Receipts = {
  next: string | null;
  receipts: Receipt[];
  subscriptions: { id: number; service: string; team: number | null }[];
  ocr_available: boolean;
  can_upload: boolean;
};
function ReceiptCard({
  receipt,
  reload,
}: {
  receipt: Receipt;
  reload: () => void;
}) {
  const [failure, setFailure] = useState(""),
    [busy, setBusy] = useState(false),
    [text, setText] = useState<string | null>(null);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFailure("");
    const fields = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await api(endpoint + `receipts/${receipt.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          ...fields,
          amount: fields.amount || null,
          issued_on: fields.issued_on || null,
        }),
      });
      reload();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!window.confirm("Delete this receipt and its file?")) return;
    setBusy(true);
    setFailure("");
    try {
      await api(endpoint + `receipts/${receipt.id}/`, { method: "DELETE" });
      reload();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  async function extract() {
    setFailure("");
    try {
      const reply = await api<{ extracted_text: string }>(
        endpoint + `receipts/${receipt.id}/`,
      );
      setText(
        reply.extracted_text ||
          "No text extracted. Enter receipt details manually or configure image OCR.",
      );
    } catch (e) {
      setFailure(showError(e));
    }
  }
  return (
    <article className={panelClass}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="break-all font-bold">{receipt.filename}</h2>
        <a className={buttonClass} href={receipt.download_url}>
          Download receipt
        </a>
      </div>
      <p className="my-3 text-sm text-slate-600">
        {receipt.extraction_status === "extracted"
          ? "Text extracted. Review the suggested details before relying on them."
          : receipt.extraction_status === "needs_ocr"
            ? "Image OCR is needed; you can enter details below."
            : "Review receipt details below."}
      </p>
      <form onSubmit={save}>
        <fieldset
          disabled={!receipt.can_edit}
          className="grid gap-3 sm:grid-cols-2"
        >
          <Field label="Merchant">
            <input
              name="merchant"
              className={inputClass}
              defaultValue={receipt.merchant}
              maxLength={100}
            />
          </Field>
          <Field label="Receipt date">
            <input
              name="issued_on"
              type="date"
              className={inputClass}
              defaultValue={receipt.issued_on ?? ""}
            />
          </Field>
          <Field label="Receipt amount">
            <input
              name="amount"
              type="number"
              step="0.01"
              min="0"
              className={inputClass}
              defaultValue={receipt.amount ?? ""}
            />
          </Field>
          <Field label="Receipt currency">
            <input
              name="currency"
              className={inputClass}
              maxLength={3}
              defaultValue={receipt.currency}
            />
          </Field>
          <Field label="Receipt note">
            <input
              name="note"
              className={inputClass}
              defaultValue={receipt.note}
              maxLength={500}
            />
          </Field>
          <button disabled={busy} className={`${buttonClass} self-end`}>
            Save receipt details
          </button>
        </fieldset>
      </form>
      <div className="mt-3 flex flex-wrap gap-3">
        <button className={buttonClass} onClick={() => void extract()}>
          View extracted text
        </button>
        {receipt.can_edit && (
          <button
            className={buttonClass}
            disabled={busy}
            onClick={() => void remove()}
          >
            Delete receipt
          </button>
        )}
      </div>
      {text !== null && (
        <pre className="mt-4 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs">
          {text}
        </pre>
      )}
      <ErrorBanner message={failure} />
    </article>
  );
}
export function ReceiptsPage() {
  const [params, setParams] = useSearchParams(),
    [failure, setFailure] = useState(""),
    [busy, setBusy] = useState(false);
  const sub = params.get("subscription"),
    charge = params.get("charge");
  const { pages, data, error, reload, next, loading, loadOlder } = useFinancePages<Receipts>("receipts/?" + params.toString());
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const updated = new URLSearchParams(params);
    for (const [name, value] of new FormData(event.currentTarget)) {
      if (typeof value === "string" && value.trim()) updated.set(name, value.trim());
      else updated.delete(name);
    }
    setParams(updated);
  }
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    if (charge) fields.set("charge", charge);
    setBusy(true);
    setFailure("");
    try {
      await api(endpoint + "receipts/", { method: "POST", body: fields });
      form.reset();
      reload();
    } catch (e) {
      setFailure(showError(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <PlanningLayout title="Receipts & invoices" workspace={false}>
      <ErrorBanner message={error || failure} />
      <p className="text-sm text-slate-600">
        Keep PDFs, PNGs and JPEGs with your subscriptions or charges. Downloads
        require your account or team membership. PDF text is extracted
        automatically; image OCR{" "}
        {data?.ocr_available ? "is available" : "requires server setup"}.
        Extracted amounts are suggestions.
      </p>
      {data?.can_upload && (
        <form
          className={`${panelClass} grid items-end gap-4 sm:grid-cols-2`}
          onSubmit={upload}
        >
          <Field label="Receipt file">
            <input
              name="file"
              className={inputClass}
              type="file"
              accept="application/pdf,image/png,image/jpeg"
              required
            />
          </Field>
          <Field label="Link to subscription">
            <select
              name="subscription"
              className={inputClass}
              defaultValue={sub ?? ""}
            >
              <option value="">Unlinked receipt</option>
              {data?.subscriptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.service}
                  {s.team ? " (team)" : ""}
                </option>
              ))}
            </select>
          </Field>
          <p className="text-xs text-slate-500">
            Up to 10 MB.{" "}
            {charge
              ? "This upload will be attached to the selected charge."
              : "Linking a subscription also shares the receipt with its team."}
          </p>
          <button className={primaryClass} disabled={busy}>
            {busy ? "Uploading…" : "Upload receipt"}
          </button>
        </form>
      )}
      <form key={params.toString()} onSubmit={filter} className={`${panelClass} grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-4`}>
        <Field label="Filter by merchant"><input name="merchant" className={inputClass} type="search" maxLength={100} defaultValue={params.get("merchant") ?? ""} /></Field>
        <Field label="Receipt date from"><input name="start" className={inputClass} type="date" defaultValue={params.get("start") ?? ""} /></Field>
        <Field label="Receipt date through"><input name="end" className={inputClass} type="date" defaultValue={params.get("end") ?? ""} /></Field>
        <button className={buttonClass}>Apply receipt filters</button>
      </form>
      {data && !data.receipts.length && (
        <p className={panelClass}>No receipts in this selection.</p>
      )}
      {pages.flatMap((page) => page.receipts).map((r) => (
        <ReceiptCard
          key={`${r.id}-${r.amount}-${r.currency}-${r.note}-${r.issued_on}`}
          receipt={r}
          reload={reload}
        />
      ))}
      {next && <button className={buttonClass} disabled={loading} onClick={loadOlder}>{loading ? "Loading…" : "Load older receipts"}</button>}
    </PlanningLayout>
  );
}

export function ReportsPage() {
  const [params, setParams] = useSearchParams();
  const query = params.toString();
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setParams(
      Object.fromEntries(
        Object.entries(values)
          .filter(([, v]) => typeof v === "string" && v)
          .map(([k, v]) => [k, String(v)]),
      ),
    );
  }
  return (
    <PlanningLayout title="Charge reports" workspace={false}>
      {params.has('charge') && <p className="text-sm text-slate-600">This report is limited to the selected charge. Apply the filters below to choose another selection.</p>}
      <p className="text-sm text-slate-600">
        Download scheduled and confirmed-paid charge history, including retained
        charges for deleted subscriptions. Reports preserve original currencies
        and payment statuses.
      </p>
      <form
        className={`${panelClass} grid gap-4 sm:grid-cols-2`}
        onSubmit={filter}
      >
        <Field label="Report workspace">
          <select
            name="scope"
            className={inputClass}
            defaultValue={params.get("scope") ?? "personal"}
          >
            <option value="personal">Personal</option>
            <option value="teams">Teams</option>
          </select>
        </Field>
        <Field label="Report service">
          <input
            name="service"
            className={inputClass}
            defaultValue={params.get("service") ?? ""}
            maxLength={100}
          />
        </Field>
        <Field label="Report from">
          <input
            name="start"
            type="date"
            className={inputClass}
            defaultValue={params.get("start") ?? ""}
          />
        </Field>
        <Field label="Report through">
          <input
            name="end"
            type="date"
            className={inputClass}
            defaultValue={params.get("end") ?? ""}
          />
        </Field>
        <Field label="Payment status">
          <select
            name="status"
            className={inputClass}
            defaultValue={params.get("status") ?? ""}
          >
            <option value="">All statuses</option>
            {["scheduled", "paid", "failed", "refunded"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <button className={`${primaryClass} self-end`}>
          Apply report filters
        </button>
      </form>
      <div className="flex flex-wrap gap-3">
        <a
          className={buttonClass}
          href={`${endpoint}reports/?${query}&filetype=csv`}
        >
          Download CSV report
        </a>
        <a
          className={buttonClass}
          href={`${endpoint}reports/?${query}&filetype=pdf`}
        >
          Download PDF report
        </a>
        <Link className={buttonClass} to="/planning/data/">
          Backup & restore
        </Link>
      </div>
      <p className="text-xs text-slate-500">
        Downloads use the applied filters. Limit: 10,000 charges per report.
      </p>
    </PlanningLayout>
  );
}

type Activity = {
  id: number;
  actor: string;
  service: string;
  action: string;
  changes: Record<string, unknown>;
  created_at: string;
};
export function ActivityPage() {
  const [params] = useSearchParams();
  const { pages, data, error, next, loading, loadOlder } = useFinancePages<{ activity: Activity[]; next: string | null }>(
    "activity/?" + params.toString(),
  );
  return (
    <PlanningLayout title="Subscription activity" workspace={false}>
      <ErrorBanner message={error} />
      <p className="text-sm text-slate-600">
        Recent subscription changes, payment updates, repayments, and team
        permission changes. Credential values stay private.
      </p>
      {data && !data.activity.length && (
        <p className={panelClass}>
          No changes recorded yet. Activity starts with this upgrade.
        </p>
      )}
      {pages.flatMap((page) => page.activity).map((a) => (
        <article className={panelClass} key={a.id}>
          <h2 className="font-bold">
            {a.service || "Team"} · {a.action.replaceAll(".", " ")}
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            {a.actor} · {new Date(a.created_at).toLocaleString()}
          </p>
          {Object.keys(a.changes).length > 0 && (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer">View changes</summary>
              <pre className="mt-2 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs">
                {JSON.stringify(a.changes, null, 2)}
              </pre>
            </details>
          )}
        </article>
      ))}
      {next && <button className={buttonClass} disabled={loading} onClick={loadOlder}>{loading ? "Loading…" : "Load older activity"}</button>}
    </PlanningLayout>
  );
}
