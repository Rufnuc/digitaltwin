import QRCode from "qrcode";
import { api, type InvoiceDetail, type InvoiceVersionRow } from "@/lib/api";

const naira = (n: number) =>
  "₦" + (Number(n) || 0).toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);

// Open a print-ready window with the company header, the invoice, every past
// version (with timing) and a QR code that traces the invoice + current version.
export async function printInvoice(inv: InvoiceDetail, versions: InvoiceVersionRow[]) {
  const [company, qr] = await Promise.all([
    api.company().catch(() => null),
    (async () => {
      const payload = JSON.stringify({
        inv: inv.invoice_number,
        id: inv.id,
        v: inv.version_no,
        total: inv.total,
        ts: new Date().toISOString(),
        url: `${window.location.origin}/invoices`,
      });
      try {
        return await QRCode.toDataURL(payload, { margin: 1, width: 140 });
      } catch {
        return "";
      }
    })(),
  ]);

  const lineRows = inv.lines
  .map(
    (ln) => `<tr>
      <td>${esc(ln.original_description || "Product")}</td>
      <td class="r">${ln.quantity}</td>
      <td class="r">${naira(ln.unit_price)}</td>
      <td class="r">${naira(ln.line_total)}</td>
    </tr>`,
  )
  .join("");


  const versionRows = versions
    .map(
      (v) => `<tr>
        <td>v${v.version_no}</td>
        <td>${esc(v.change_note ?? "—")}</td>
        <td>${esc(v.changed_by ?? "—")}</td>
        <td>${v.changed_at ? esc(new Date(v.changed_at).toLocaleString()) : "—"}</td>
        <td class="r">${naira((v.snapshot as { total?: number }).total ?? 0)}</td>
      </tr>`,
    )
    .join("");

  const c = company;
  const companyBlock = c
    ? `<div class="co">
        <div class="co-name">${esc(c.name || "Your Company")}</div>
        ${c.address ? `<div>${esc(c.address)}</div>` : ""}
        <div>${[c.phone, c.email, c.website].filter(Boolean).map(esc).join(" · ")}</div>
        ${c.tax_id ? `<div>Tax ID: ${esc(c.tax_id)}</div>` : ""}
      </div>`
    : `<div class="co"><div class="co-name">Your Company</div><div class="muted">Set your company details in Settings.</div></div>`;

  const html = `<!doctype html><html><head><meta charset="utf-8"><title>${esc(inv.invoice_number)}</title>
  <style>
    * { box-sizing: border-box; }
    body { font: 13px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; color: #111; margin: 32px; }
    .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }
    .co-name { font-size: 18px; font-weight: 700; }
    .muted { color: #666; }
    h1 { font-size: 20px; margin: 0 0 2px; }
    .meta { text-align: right; }
    .qr { text-align: right; margin-top: 8px; }
    .qr img { width: 120px; height: 120px; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { padding: 6px 8px; border-bottom: 1px solid #ddd; text-align: left; }
    th { background: #f4f4f5; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
    .r { text-align: right; }
    .totals { margin-top: 12px; margin-left: auto; width: 260px; }
    .totals td { border: none; padding: 2px 8px; }
    .grand { font-weight: 700; border-top: 1px solid #111 !important; }
    h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: #555; margin: 28px 0 4px; }
    .foot { margin-top: 32px; color: #666; font-size: 11px; border-top: 1px solid #ddd; padding-top: 8px; }
    @media print { body { margin: 12mm; } .noprint { display: none; } }
  </style></head><body>
    <div class="top">
      ${companyBlock}
      <div class="meta">
        <h1>INVOICE</h1>
        <div><strong>${esc(inv.invoice_number)}</strong></div>
        <div>Date: ${esc(inv.invoice_date)}</div>
        <div>Version: v${inv.version_no}</div>
        <div class="muted">Bill to: ${esc(inv.customer_name ?? "Walk-in")}</div>
        <div class="qr">${qr ? `<img src="${qr}" alt="trace QR"/>` : ""}<div class="muted" style="font-size:10px">scan to trace</div></div>
      </div>
    </div>

    <table>
      <thead><tr><th>Description</th><th class="r">Qty</th><th class="r">Unit</th><th class="r">Amount</th></tr></thead>
      <tbody>${lineRows}</tbody>
    </table>

    <table class="totals">
      <tr><td>Subtotal</td><td class="r">${naira(inv.subtotal)}</td></tr>
      <tr><td>Tax</td><td class="r">${naira(inv.tax)}</td></tr>
      ${inv.shipping ? `<tr><td>Shipping${inv.shipping_note ? ` (${esc(inv.shipping_note)})` : ""}</td><td class="r">${naira(inv.shipping)}</td></tr>` : ""}
      <tr><td>Discount</td><td class="r">-${naira(inv.discount)}</td></tr>
      <tr class="grand"><td>Total</td><td class="r">${naira(inv.total)}</td></tr>
    </table>

    <h2>Version history (${versions.length})</h2>
    <table>
      <thead><tr><th>Version</th><th>Change</th><th>By</th><th>When</th><th class="r">Total</th></tr></thead>
      <tbody>${versionRows || `<tr><td colspan="5" class="muted">No prior versions recorded.</td></tr>`}</tbody>
    </table>

    <div class="foot">
      ${c?.footer_note ? esc(c.footer_note) + "<br/>" : ""}
      Raised by ${esc(inv.created_by ?? "—")}. Generated ${esc(new Date().toLocaleString())}.
      This document lists every recorded version of the invoice; versions are immutable.
    </div>
    <script>window.onload = function(){ setTimeout(function(){ window.print(); }, 150); };</script>
  </body></html>`;

  const w = window.open("", "_blank", "width=860,height=960");
  if (!w) {
    alert("Please allow pop-ups to print the invoice.");
    return;
  }
  w.document.write(html);
  w.document.close();
}
