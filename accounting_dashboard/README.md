# Accounting Dashboard — Odoo 18

A modern, interactive Accounting Dashboard for Odoo 18, modeled on the
reference mockup you provided.

## Features

- **5 KPI cards**: Cash in Bank, Accounts Receivable, Revenue Total,
  Expenses Total, Net Total — with pastel icon chips and live values.
- **Revenue & Expense Summary tables** with source badges
  (`Auto from Odoo`, `Manual / Google Sheet`, `Automatic`).
- **Revenue Trend** — purple area-line chart of the last 6 months.
- **Expense Trend** — orange bar chart of the last 6 months.
- **Net Summary** — green donut showing net margin %, plus split of
  Revenue / Expenses / Net Total.
- **Recent Expense Entries** — last 4 manual / Google-Sheet entries,
  with a "View All" link to the full list.
- **Period filter**: `This Month`, `This Quarter`, `This Year`.
- **Multi-company aware** — uses the active company from Odoo's company
  switcher.
- **Refresh button** to re-pull all data.

## Tech stack

- 100% **Odoo 18 OWL** component (no jQuery, no widget legacy).
- Charts are **pure SVG**, hand-drawn in the component — no external
  chart.js / d3 / recharts dependency required.
- All data comes from `account.move` / `account.move.line` (posted only)
  and the new `accounting.dashboard.expense` model for manual entries.
- Multi-currency: respects the active company currency.

## Install

1. Copy the `accounting_dashboard` folder into your Odoo `addons` path.
2. Restart Odoo with `-u accounting_dashboard` (or update the apps list
   in the UI and click *Install*).
3. Open the **Accounting Dashboard** menu in the top app bar.

## Adding manual / Google-Sheet expenses

Navigate to **Accounting Dashboard → Configuration → Expense Entries**
and create rows. They are immediately reflected in the dashboard's
*Expense Summary*, *Expense Trend* and *Recent Expense Entries*.

## File layout

```
accounting_dashboard/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── main.py                  # JSON endpoint (optional)
├── models/
│   ├── __init__.py
│   ├── dashboard.py             # AbstractModel: data aggregator
│   └── expense_entry.py         # accounting.dashboard.expense
├── security/
│   └── ir.model.access.csv
├── views/
│   ├── dashboard_menus.xml      # Client action + menus
│   └── expense_entry_views.xml  # List/Form/Search for expense entries
└── static/
    ├── description/
    │   ├── icon.png
    │   └── icon.svg
    └── src/
        ├── js/dashboard.js      # OWL component
        ├── scss/dashboard.scss  # Styles
        └── xml/dashboard.xml    # OWL template
```

## Notes

- If your DB has no posted journal entries yet, the dashboard shows
  illustrative figures (matching the mockup) so the UI is never blank.
  As soon as real `account.move` data exists, those figures are
  replaced automatically.
- Numbers in KPIs respect the active company's currency symbol.
