"""Detailed knowledgebase how-to guides (owner/staff facing).

Kept separate from the seeder so the content is easy to maintain. Each entry is
(title, category, body-markdown) and is seeded as a single article. Bump
CONTENT_VERSION in seed_kb_history.py whenever these change so they refresh on deploy.
"""
from __future__ import annotations

GUIDES: list[tuple[str, str, str]] = [
    # ----------------------------------------------------------------- Getting started
    ("Getting started: a tour of the app", "Getting Started",
     "# Getting started\n\n"
     "![The app layout: sidebar, main area and dashboard](/api/v1/kb/assets/overview.svg)\n\n"
     "Welcome. This app runs your whole business — sales, stock, customers, suppliers, "
     "money and reporting — in one place. This guide orients you; the other articles go "
     "deep on each area.\n\n"
     "## Logging in\n"
     "1. Open the web address for your business and sign in with your email and password.\n"
     "2. If you forget your password, an Owner or Admin can reset it for you (Settings → "
     "users).\n\n"
     "## The layout\n"
     "- **Left sidebar** — every area of the app, grouped into sections (Overview, Sales & "
     "Money, Inventory & Suppliers, Intelligence, Data & Settings). What you see depends on "
     "your role.\n"
     "- **Main area** — the screen you're working on.\n"
     "- **Top bar** — notifications and your account.\n\n"
     "## The golden rules of this app\n"
     "- **Nothing is deleted.** Mistakes are corrected with a trail — invoices are *voided*, "
     "records are *archived*. You can always see what happened and who did it.\n"
     "- **Stock is real.** Selling draws stock from a specific location, oldest batch first, "
     "and every unit traces back to the customer who bought it.\n"
     "- **Every change is logged.** The **Activity Log** records who did what and when.\n\n"
     "## A typical day\n"
     "1. Check the **Dashboard** for sales, cash and anything that needs attention.\n"
     "2. Record sales as they happen under **New Sale**.\n"
     "3. Take payments (cash, transfer or POS card) against invoices.\n"
     "4. Receive new stock when deliveries arrive.\n"
     "5. Review **Receivables** (who owes you) and the **Action List** (what to reorder).\n\n"
     "> Tip: the **Benfieg** AI assistant can answer questions about your own data in plain "
     "language — try “which customers owe me the most?”"),

    ("Understanding roles and permissions", "Administration",
     "# Roles and permissions\n\n"
     "Everyone who uses the app has a **role** that decides what they can see and do. From "
     "most to least powerful:\n\n"
     "- **Owner** — you, the business owner. Can do everything, including managing users.\n"
     "- **Admin** — technical administrator; same broad access as Owner for day-to-day work.\n"
     "- **Manager** — runs operations: sales, stock, suppliers, receivables, reports, the "
     "knowledgebase and the Team Map.\n"
     "- **Staff** — records sales and payments, receives stock, manages customers.\n"
     "- **Salesgirl** — a restricted front-desk role for selling: raise invoices and "
     "waybills, add customers, record payments. It deliberately can't reach manager-level "
     "areas, but everything it does is logged.\n\n"
     "## Managing users\n"
     "1. Go to **Settings** (Owner/Admin).\n"
     "2. Add a user with their email and role, or reset a password.\n"
     "3. Each person signs in with their own account so the audit trail shows exactly who "
     "did what.\n\n"
     "> Give each person the lowest role that lets them do their job. You can always raise "
     "it later."),

    ("The Dashboard explained", "Getting Started",
     "# The Dashboard\n\n"
     "The Dashboard is your morning glance at the business. It shows headline numbers "
     "(**KPIs**) and shortcuts into the areas that need you.\n\n"
     "## What the numbers mean\n"
     "- **Revenue / sales** — the value of sales recorded.\n"
     "- **Profit** — revenue minus cost of goods sold and expenses (an estimate from your "
     "recorded costs).\n"
     "- **Orders / units sold** — how many sales and how many items.\n"
     "- **Inventory value** — what your stock on hand is worth, from the stock ledger.\n"
     "- **Active customers** — customers marked active.\n\n"
     "## If you see a DEMO banner\n"
     "A banner appears while the only data present is sample/demo data, so you never mistake "
     "practice numbers for real ones. Once you enter real sales it reflects reality. An "
     "Owner/Admin can clear demo data from Settings.\n\n"
     "> Numbers update as you record sales, payments and stock — there's nothing to “save”."),

    # ----------------------------------------------------------------- Sales & invoicing
    ("Managing customers", "Sales & Invoicing",
     "# Customers\n\n"
     "Customers are the people and businesses you sell to. Good customer records make "
     "invoicing, credit and follow-up easy.\n\n"
     "## Add a customer\n"
     "1. Go to **Customers** → **New** (or just type a new name while recording a sale and "
     "it's created for you).\n"
     "2. Fill in name and any details you have: phone, location, customer type (retail, "
     "wholesale, trade), and **payment terms** (days) if you give them credit.\n\n"
     "## What a customer record shows\n"
     "- Their **lifetime revenue**, order count and first/last purchase.\n"
     "- Their **outstanding balance** (what they owe) and a running **statement** of invoices "
     "and payments.\n\n"
     "## Credit terms\n"
     "If a customer has payment terms (e.g. 30 days), a credit sale to them gets a due date "
     "that far out, and it will show in **Receivables** aging once overdue.\n\n"
     "> You can start a customer with just a name and fill in the rest later."),

    ("Recording a sale (step by step)", "Sales & Invoicing",
     "# Record a sale\n\n"
     "![The New Sale screen](/api/v1/kb/assets/sale.svg)\n\n"
     "Use **New Sale** whenever a customer buys goods. This both bills the customer and "
     "draws the goods from your stock.\n\n"
     "## Steps\n"
     "1. Open **New Sale** (also reachable from Invoices).\n"
     "2. The **invoice number** is filled automatically; set the **date** if it isn't today.\n"
     "3. **Customer** — search and pick an existing customer, or type a new name to create "
     "one on the spot. Leave blank for a walk-in.\n"
     "4. **Sell from** — choose the location you're selling out of (your Home/Office point of "
     "sale). Stock is drawn from here.\n"
     "5. **Items** — for each line pick the product, the **quantity** and the **unit price**. "
     "The price pre-fills from the product's selling price; you can change it. The stock on "
     "hand at that location shows next to the line.\n"
     "6. Add **Tax**, **Discount** or **Shipping** if any (a shipping note explains the "
     "charge).\n"
     "7. Review the total, then click **Record sale & draw stock**.\n\n"
     "## What happens behind the scenes\n"
     "- Stock is reduced **oldest batch first (FIFO)**, and every unit is traced to this "
     "customer and invoice.\n"
     "- An invoice is created, ready to print and to take payment against.\n"
     "- If the customer has credit terms, a **due date** is set automatically.\n\n"
     "## Common issues\n"
     "- *“Only N in stock”* — you're trying to sell more than you have at that location. "
     "Receive more stock, transfer some in, or reduce the quantity.\n"
     "- *Bought from another seller to resell?* Use **+ Item from another seller** to add it "
     "to stock first, then sell it.\n\n"
     "> Selling here moves stock. To bill for something that is NOT stock (a service), that's "
     "a non-stock invoice — ask a manager."),

    ("Working with invoices", "Sales & Invoicing",
     "# Invoices\n\n"
     "![The invoice panel and its actions](/api/v1/kb/assets/invoice.svg)\n\n"
     "Every sale creates an invoice. The **Invoices & Sales** screen lists them with search, "
     "filters (by payment status, verification) and sorting.\n\n"
     "## Open an invoice\n"
     "Click a row to open the invoice panel. You'll see the customer, the line items (with "
     "the real product names), totals, payment status and balance, any payments recorded, "
     "and any waybills raised.\n\n"
     "## Editing\n"
     "Managers (and the front-desk role) can **Edit** an invoice. Every edit is saved as a "
     "new **version** — the full history is kept and visible, so nothing is lost. You cannot "
     "silently change a paid invoice's amounts or a fulfilled invoice's lines; use **Void** "
     "or **Return** instead (see those guides).\n\n"
     "## Printing\n"
     "- **Print for customer** — a clean copy *without* the internal edit history.\n"
     "- **Print (with history)** — an internal copy that includes every version, for your "
     "records.\n\n"
     "## Version history\n"
     "The panel lists every version with who changed it, when, and the total at that point. "
     "It's your proof of exactly how an invoice evolved.\n\n"
     "> The payment line shows **Paid in full**, **Owing ₦X**, **Refund due ₦X** (you owe "
     "the customer) or **Void**."),

    ("Voiding an invoice and refunds", "Sales & Invoicing",
     "# Void an invoice\n\n"
     "Voiding cancels an invoice completely — use it for a mistake or a cancelled sale.\n\n"
     "## How\n"
     "1. Open the invoice.\n"
     "2. Click **Void invoice** (Managers and above).\n"
     "3. Enter a reason and confirm.\n\n"
     "## What voiding does\n"
     "- **Returns the stock** the sale drew back into your warehouse.\n"
     "- **Refunds the customer**: any payments recorded against it are reversed, so the "
     "invoice settles at **₦0** — never a negative balance.\n"
     "- **Removes it from sales and receivables** so your numbers are correct.\n"
     "- **Keeps the record**, marked VOID, with its history. It is never deleted.\n\n"
     "> Use Void to clean up test invoices or a wrong sale. For a customer bringing back "
     "*some* goods, use **Return items** instead."),

    ("Customer returns", "Sales & Invoicing",
     "# Process a customer return\n\n"
     "Use returns when a customer brings goods back (wrong item, damaged, change of mind) "
     "but you're not cancelling the whole sale.\n\n"
     "## How\n"
     "1. Open the invoice and click **Return items**.\n"
     "2. Choose the **warehouse/location** to put the returned goods back into.\n"
     "3. Enter the **quantity returned** for each item (you can return part of a line, and "
     "return again later).\n"
     "4. Add a reason and confirm.\n\n"
     "## What happens\n"
     "- The returned units go **back into stock**.\n"
     "- The invoice total and what the customer owes are **reduced** by the returned value.\n"
     "- If the customer had already paid, the balance shows **Refund due ₦X** so you know to "
     "give money back.\n\n"
     "> Returns are validated against what's still on the invoice, so you can't return more "
     "than was sold."),

    # ----------------------------------------------------------------- Payments
    ("Receivables and recording payments", "Payments",
     "# Receivables & payments\n\n"
     "**Receivables** is the money customers owe you. Record every payment so balances and "
     "aging stay correct.\n\n"
     "## Record a payment\n"
     "1. Open the invoice (or find the customer) and click **Record payment**.\n"
     "2. Enter the **amount** (full or part), the **method** (cash, transfer, POS, etc.) and "
     "a reference if any.\n"
     "3. For a bank transfer, add the transaction ID and from/to account for full "
     "traceability.\n"
     "4. Save. The invoice updates to **Paid**, **Partial** (with the remaining balance) and "
     "records **who** took the payment and when.\n\n"
     "## The Receivables screen\n"
     "- **Total outstanding** and an **aging** breakdown (current, 1–30, 31–60, 61–90, 90+ "
     "days overdue).\n"
     "- **Top debtors** — who owes the most.\n"
     "- A per-customer **statement** showing invoices and payments as a running balance.\n\n"
     "## Overpayment protection\n"
     "You can't record more than the outstanding balance. If a customer overpays in reality, "
     "it points to a data issue — check the invoice.\n\n"
     "> Card payments on your POS machine can be recorded here too, but see the POS guide for "
     "the automatic way."),

    ("Card payments on the POS machine (Moniepoint)", "Payments",
     "# POS card payments\n\n"
     "![The POS Payments reconciliation screen](/api/v1/kb/assets/pos.svg)\n\n"
     "The app can link card payments taken on your Moniepoint terminal to the right invoice "
     "— for full and part payments.\n\n"
     "## The easy way: charge from the invoice\n"
     "1. Open the invoice and click **Charge on POS (Moniepoint)**.\n"
     "2. Enter the amount. Then either:\n"
     "   - **Push to terminal** (enter the terminal ID) to make the amount pop up on the "
     "machine ready to collect; or\n"
     "   - **Expect only** — you charge on the terminal yourself as usual.\n"
     "3. When the customer pays, the transaction **links to the invoice automatically** and "
     "records the payment.\n\n"
     "## Anything that didn't link: the POS Payments screen\n"
     "Open **POS Payments** to see card transactions that couldn't be matched. Each shows "
     "suggested invoices — one tap to **assign** it. You can also assign by invoice number, "
     "or **ignore** a transaction that isn't a sale.\n\n"
     "## Safety flags\n"
     "The screen warns about a **possible duplicate** (same amount + terminal within minutes) "
     "and an **unusually large** amount, so you check before linking.\n\n"
     "## One-time setup (developer)\n"
     "Automatic linking needs your Moniepoint webhook + API details configured on the server. "
     "Until then it works in manual mode (Expect + the POS Payments screen).\n\n"
     "> A part payment on the POS sets the invoice to **Partial** with the balance still "
     "owing — just like any other partial payment."),

    # ----------------------------------------------------------------- Inventory
    ("Products and your catalogue", "Inventory",
     "# Products\n\n"
     "Products are the items you buy and sell. A good catalogue drives stock, pricing and "
     "reorder suggestions.\n\n"
     "## Add / edit a product\n"
     "1. Go to **Products** → **New**.\n"
     "2. Set the **code** (unique), **name**, **category**, **purchase cost** and **selling "
     "price**, and a **reorder level** if you want low-stock alerts.\n\n"
     "## What you can see per product\n"
     "- Current **on-hand** quantity and stock **value**.\n"
     "- A **history** timeline (searchable) of movements and changes.\n"
     "- **Substitutes** — cross-brand alternatives to offer when something is out.\n\n"
     "> The selling price here pre-fills the price when you add the product to a sale."),

    ("Receiving stock, warehouses and transfers", "Inventory",
     "# Stock, warehouses and transfers\n\n"
     "Stock is tracked in **batches (lots)** per location, so you always know what you have, "
     "where, what it cost, and where it came from.\n\n"
     "## Locations\n"
     "You have **warehouses** (storage) and **points of sale** (Home/Office shops you sell "
     "from). Add a point of sale on the New Sale screen with **+ Add a sale location**.\n\n"
     "## Receive stock (a delivery arrives)\n"
     "1. Go to **Inventory** (or use **+ Item from another seller** on New Sale for a quick "
     "receive).\n"
     "2. Enter the product, quantity, and **what you paid per unit** (the cost basis), plus "
     "the supplier or a reference if you have one.\n"
     "3. This creates a new batch and adds it to the location's on-hand.\n\n"
     "## Transfer between locations\n"
     "Move stock from a warehouse to a shop (or between warehouses). The batch's history "
     "(received date, supplier, cost) is preserved so traceability is never lost.\n\n"
     "## Why batches matter\n"
     "- Sales draw the **oldest batch first (FIFO)**.\n"
     "- Each batch carries its **cost**, which is how profit (COGS) is calculated.\n"
     "- You can trace any unit back to its delivery and forward to its buyer.\n\n"
     "> **Inventory** shows per-product levels with search, a low-stock filter and value."),

    ("Reorder Action List and planning", "Inventory",
     "# Knowing what to reorder\n\n"
     "The app's quant engine forecasts demand and tells you what to restock, ranked by the "
     "money at risk if you run out.\n\n"
     "## Action List\n"
     "Open **Action List** for a plain, prioritised list of what to reorder and roughly how "
     "much, considering demand, lead time and a safety buffer. The most financially important "
     "items come first.\n\n"
     "## Behind it\n"
     "- **ABC classes** protect your most valuable items with higher stock cover.\n"
     "- **Lead-time variability** is built into the safety stock.\n"
     "- New products get a careful **cold-start** estimate from similar items.\n\n"
     "> Ask **Benfieg** things like “what should I reorder this week within ₦500,000?”"),

    # ----------------------------------------------------------------- Suppliers & logistics
    ("Suppliers and procurement", "Suppliers & Procurement",
     "# Suppliers & procurement\n\n"
     "## Suppliers\n"
     "Under **Suppliers** keep your sellers' details, see a **statement** of what you owe and "
     "have paid (with receipts), their shipments, and slow-moving items you bought from them.\n\n"
     "## Procurement flow\n"
     "1. Build a **request list** of what you need.\n"
     "2. Turn it into an **order** to a supplier.\n"
     "3. **Receive** the goods when they arrive, including transport cost, which flows into "
     "the landed cost of the stock.\n\n"
     "## Supplier payments\n"
     "Record what you pay suppliers so payables and cash flow stay accurate.\n\n"
     "> Import many suppliers at once with a CSV under **Imports**."),

    ("Waybills and dispatch", "Suppliers & Procurement",
     "# Waybills (dispatch)\n\n"
     "A waybill records goods leaving to a customer against an invoice.\n\n"
     "## Raise a waybill\n"
     "1. Open the invoice and click **Create waybill**.\n"
     "2. It's linked to the invoice; you can raise another if a delivery goes in parts.\n\n"
     "The invoice panel shows each waybill's number, status and dispatch date, and the "
     "**Waybills** screen lists them all.\n\n"
     "> Use waybills so you can prove what was dispatched, when, and for which sale."),

    # ----------------------------------------------------------------- Finance
    ("Expenses, cash flow and tax", "Finance",
     "# Money: expenses, cash flow & tax\n\n"
     "## Expenses\n"
     "Record business costs (rent, fuel, salaries, etc.) under **Expenses** so profit and "
     "cash flow reflect reality.\n\n"
     "## Cash Flow\n"
     "The **Cash Flow** screen shows money in (sales/payments) versus money out (supplier "
     "payments, expenses) over a period, so you can see whether cash is building or draining.\n\n"
     "## Tax\n"
     "The **Tax** screen estimates **VAT (7.5%)** and **company income tax** (tiered by "
     "turnover) from your data.\n\n"
     "> These are **estimates to guide you, not official tax advice** — confirm figures with "
     "your accountant before filing."),

    # ----------------------------------------------------------------- Intelligence
    ("Benfieg: the AI assistant", "Intelligence",
     "# Benfieg (AI assistant)\n\n"
     "Benfieg answers questions about **your own business data** in plain language and can "
     "run the app's analysis tools for you.\n\n"
     "## Using it\n"
     "1. Open **Benfieg (AI)**.\n"
     "2. Ask in normal words, e.g. “Which products are about to run out?”, “Who owes me "
     "the most?”, “What was my profit last month?”, “What should I reorder?”\n"
     "3. Benfieg shows its answer with the **source** of each figure so you can trust it.\n\n"
     "## Good to know\n"
     "- It only uses your real data and clearly separates facts from estimates.\n"
     "- Your past conversations are saved so you can reopen them.\n"
     "- For actions that change data, it asks you to confirm first.\n\n"
     "> Be specific for the best answer — include a time period or a customer/product name."),

    ("Market Intelligence", "Intelligence",
     "# Market Intelligence\n\n"
     "This screen brings in **real external data for Nigeria** — economic indicators (World "
     "Bank), live exchange rates, and relevant business news — each kept with its source and "
     "date.\n\n"
     "## Refresh\n"
     "Click **Refresh from sources** to pull the latest. Figures come with an honest note "
     "that any “possible impact” is an assumption, not a certainty.\n\n"
     "## If it can't fetch\n"
     "Click **Test data sources** to check, from the server, which sources are reachable. If "
     "all fail, the server has no outbound internet (a hosting setting); if only some fail, "
     "that source is blocking the server. Share the result with your developer.\n\n"
     "> Use it to anticipate cost pressure — a weaker naira raises the cost of imported "
     "parts, for example."),

    # ----------------------------------------------------------------- Administration
    ("Team Map: staff location", "Administration",
     "# Team Map\n\n"
     "![The Team Map with addressed pins and a team list](/api/v1/kb/assets/teammap.svg)\n\n"
     "Managers can see where team members are while they're logged in on a company device, "
     "shown as a **readable address** on a live map.\n\n"
     "## Using it\n"
     "1. Open **Team Map**.\n"
     "2. Each person's latest location shows as a pin and in the side list.\n"
     "3. Click a person to see their recent **movement trail**.\n\n"
     "Meaningful moves are also written to the **Activity Log** with the address and time.\n\n"
     "## Important limits (please read)\n"
     "- The device must **grant location permission** once, and the app must be **open** — a "
     "website cannot track anyone in the background or when closed.\n"
     "- This is intended for **company devices** with staff aware of it.\n\n"
     "> If a pin is missing, that person hasn't logged in on a location-enabled device yet."),

    ("Activity Log and the audit trail", "Administration",
     "# Activity Log\n\n"
     "The **Activity Log** is an automatic, complete record of every change in the app: who "
     "did what, when, and the before → after.\n\n"
     "## Using it\n"
     "- Filter by user or action, and export the log.\n"
     "- Use it to answer “who changed this price / voided that invoice / recorded this "
     "payment?”\n\n"
     "> You don't create entries — they're written automatically as people work. It's your "
     "proof of record."),

    ("Imports and documents", "Administration",
     "# Imports & documents\n\n"
     "## Imports\n"
     "Bring existing data in from spreadsheets under **Imports** — download a template, fill "
     "it, and upload (suppliers, for example). The app validates before importing.\n\n"
     "## Documents\n"
     "Upload scanned invoices and paperwork under **Documents**; the app can read machine-"
     "readable documents and keep them with their provenance.\n\n"
     "> Start with a small test file to check your columns map correctly before a big import."),

    ("Company settings and your profile", "Administration",
     "# Settings\n\n"
     "Under **Settings** you manage the business profile and (as Owner/Admin) users.\n\n"
     "## Company profile\n"
     "Set your **business name, address, phone, email, website, tax ID** and an optional "
     "**footer note**. These appear on printed invoices — fill them in before sending "
     "invoices to customers.\n\n"
     "## Users\n"
     "Add staff, set their role, and reset passwords. Each person should have their own "
     "login so the audit trail is accurate.\n\n"
     "## Appearance\n"
     "Switch between light and dark mode from the top bar.\n\n"
     "> Keep your company details current — they're what your customers see on every invoice."),
]
