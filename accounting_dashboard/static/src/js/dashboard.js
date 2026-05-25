/** @odoo-module **/

import { Component, onWillStart, onMounted, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class AccountingDashboard extends Component {
    static template = "accounting_dashboard.Dashboard";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.companyService = useService("company");

        this.state = useState({
            loading: true,
            period: "this_month",
            data: null,
            error: null,
        });

        this.revenueChartRef = useRef("revenueChart");
        this.expenseChartRef = useRef("expenseChart");
        this.donutRef = useRef("donutChart");

        onWillStart(async () => {
            await this._fetchData();
        });

        onMounted(() => {
            this._drawCharts();
        });
    }

    // -------------------------------------------------------------------------
    // Data
    // -------------------------------------------------------------------------
    async _fetchData() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call(
                "accounting.dashboard",
                "get_dashboard_data",
                [],
                {
                    period: this.state.period,
                    company_id: this.companyService.currentCompany.id,
                }
            );
            this.state.data = data;
        } catch (err) {
            console.error(err);
            this.state.error = _t("Failed to load dashboard data");
        } finally {
            this.state.loading = false;
        }
    }

    async onPeriodChange(ev) {
        this.state.period = ev.target.value;
        await this._fetchData();
        // wait a tick for DOM, then redraw
        setTimeout(() => this._drawCharts(), 50);
    }

    async refresh() {
        await this._fetchData();
        setTimeout(() => this._drawCharts(), 50);
    }

    // -------------------------------------------------------------------------
    // Formatting helpers used from the template
    // -------------------------------------------------------------------------
    formatCurrency(amount) {
        if (amount === undefined || amount === null) return "$ 0.00";
        const sym = (this.state.data && this.state.data.currency.symbol) || "$";
        const num = Number(amount).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return `${sym} ${num}`;
    }

    formatDate(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        return d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
    }

    // -------------------------------------------------------------------------
    // Chart drawing (pure SVG — no chart.js dependency, works offline)
    // -------------------------------------------------------------------------
    _drawCharts() {
        if (!this.state.data) return;
        this._drawRevenueLine();
        this._drawExpenseBars();
        this._drawDonut();
    }

    _drawRevenueLine() {
        const svg = this.revenueChartRef.el;
        if (!svg) return;
        const trend = this.state.data.revenue_trend;
        const width = svg.clientWidth || 600;
        const height = 260;
        const padding = { top: 20, right: 30, bottom: 30, left: 50 };
        const innerW = width - padding.left - padding.right;
        const innerH = height - padding.top - padding.bottom;

        const max = Math.max(...trend.map(t => t.value), 1);
        const niceMax = Math.ceil(max / 100000) * 100000;
        const stepY = niceMax / 5;

        const xStep = innerW / (trend.length - 1);
        const points = trend.map((t, i) => {
            const x = padding.left + i * xStep;
            const y = padding.top + innerH - (t.value / niceMax) * innerH;
            return { x, y, ...t };
        });

        const pathLine = points
            .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
            .join(" ");

        const pathArea = `${pathLine} L ${points[points.length - 1].x} ${padding.top + innerH} L ${points[0].x} ${padding.top + innerH} Z`;

        svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
        svg.innerHTML = `
            <defs>
                <linearGradient id="revArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#a855f7" stop-opacity="0.35"/>
                    <stop offset="100%" stop-color="#a855f7" stop-opacity="0.02"/>
                </linearGradient>
            </defs>
            ${[0,1,2,3,4,5].map(i => {
                const y = padding.top + innerH - (i * stepY / niceMax) * innerH;
                const label = (i * stepY / 1000).toFixed(0) + "K";
                return `<g>
                    <line x1="${padding.left}" y1="${y}" x2="${padding.left + innerW}" y2="${y}" stroke="#f1f1f4" stroke-width="1"/>
                    <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" font-size="11" fill="#9ca3af">${label}</text>
                </g>`;
            }).join("")}
            <path d="${pathArea}" fill="url(#revArea)"/>
            <path d="${pathLine}" fill="none" stroke="#a855f7" stroke-width="2.5" stroke-linejoin="round"/>
            ${points.map(p => `<circle cx="${p.x}" cy="${p.y}" r="4" fill="#a855f7" stroke="white" stroke-width="2"/>`).join("")}
            ${points.map(p => `<text x="${p.x}" y="${height - 8}" text-anchor="middle" font-size="11" fill="#6b7280">${p.month}</text>`).join("")}
        `;
    }

    _drawExpenseBars() {
        const svg = this.expenseChartRef.el;
        if (!svg) return;
        const trend = this.state.data.expense_trend;
        const width = svg.clientWidth || 600;
        const height = 260;
        const padding = { top: 20, right: 30, bottom: 30, left: 50 };
        const innerW = width - padding.left - padding.right;
        const innerH = height - padding.top - padding.bottom;

        const max = Math.max(...trend.map(t => t.value), 1);
        const niceMax = Math.ceil(max / 50000) * 50000;
        const stepY = niceMax / 6;

        const slot = innerW / trend.length;
        const barW = slot * 0.45;

        svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
        svg.innerHTML = `
            <defs>
                <linearGradient id="expBar" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#fb923c"/>
                    <stop offset="100%" stop-color="#f97316"/>
                </linearGradient>
            </defs>
            ${[0,1,2,3,4,5,6].map(i => {
                const y = padding.top + innerH - (i * stepY / niceMax) * innerH;
                const label = (i * stepY / 1000).toFixed(0) + "K";
                return `<g>
                    <line x1="${padding.left}" y1="${y}" x2="${padding.left + innerW}" y2="${y}" stroke="#f1f1f4" stroke-width="1"/>
                    <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" font-size="11" fill="#9ca3af">${label}</text>
                </g>`;
            }).join("")}
            ${trend.map((t, i) => {
                const cx = padding.left + slot * i + slot / 2;
                const h = (t.value / niceMax) * innerH;
                const x = cx - barW / 2;
                const y = padding.top + innerH - h;
                return `
                    <rect x="${x}" y="${y}" width="${barW}" height="${h}" rx="4" fill="url(#expBar)">
                        <title>${t.month}: ${t.value.toLocaleString()}</title>
                    </rect>
                    <text x="${cx}" y="${height - 8}" text-anchor="middle" font-size="11" fill="#6b7280">${t.month}</text>
                `;
            }).join("")}
        `;
    }

    _drawDonut() {
        const svg = this.donutRef.el;
        if (!svg) return;
        const margin = this.state.data.net_summary.margin || 0;
        const size = 160;
        const stroke = 14;
        const r = (size - stroke) / 2;
        const cx = size / 2;
        const cy = size / 2;
        const circ = 2 * Math.PI * r;
        const pct = Math.max(0, Math.min(100, margin));
        const offset = circ * (1 - pct / 100);

        svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
        svg.innerHTML = `
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#e6f4ef" stroke-width="${stroke}"/>
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#10b981" stroke-width="${stroke}"
                    stroke-linecap="round" stroke-dasharray="${circ}" stroke-dashoffset="${offset}"
                    transform="rotate(-90 ${cx} ${cy})"/>
            <text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="22" font-weight="600" fill="#0f766e">${pct.toFixed(2)}%</text>
            <text x="${cx}" y="${cy + 18}" text-anchor="middle" font-size="11" fill="#6b7280">Margin</text>
        `;
    }

    // -------------------------------------------------------------------------
    // Navigation actions for KPI cards & "View All"
    // -------------------------------------------------------------------------
    openExpenseEntries() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Expense Entries"),
            res_model: "accounting.dashboard.expense",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("accounting_dashboard", AccountingDashboard);
