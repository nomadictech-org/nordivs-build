/** @odoo-module **/

import { NavBar } from "@web/webclient/navbar/navbar";
import { useService, useBus } from "@web/core/utils/hooks";
import { useState, useEffect, useRef } from "@odoo/owl";

/**
 * Navbar with a single iOS-style back button on the left.
 *
 * Behaviour:
 *   - On the dashboard (home menu shown): the back button AND all app content
 *     in the navbar (brand, section menus, breadcrumb) are hidden.
 *   - Inside an app: the back button is shown; clicking it returns to the
 *     dashboard.
 *
 * We drive visibility BOTH from CSS (body.o_home_menu_background) and
 * imperatively from JS here, so it is robust against CSS specificity / asset
 * ordering issues. The JS reads `hm.hasHomeMenu` reactively and re-applies on
 * every HOME-MENU:TOGGLED event.
 */
export class OwnBrandNavBar extends NavBar {
    static template = "own_brand.NavBar";

    setup() {
        super.setup();
        this.hm = useState(useService("home_menu"));
        this.navRef = useRef("nav");
        this.backBtnRef = useRef("backBtn");
        useBus(this.env.bus, "HOME-MENU:TOGGLED", () => this._applyVisibility());
        // Runs after every render so refs are populated and state is current.
        useEffect(() => this._applyVisibility());
    }

    /** True when an application is open (home menu is NOT displayed). */
    get isInApp() {
        return !this.hm.hasHomeMenu;
    }

    /** Back button handler: return to the dashboard (home menu). */
    _onBackToDashboard() {
        this.hm.toggle(true);
    }

    /**
     * Show/hide the back button and the app-owned navbar content depending on
     * whether we are in an app or on the dashboard.
     */
    _applyVisibility() {
        const inApp = this.isInApp;

        // Back button: visible only in an app.
        if (this.backBtnRef.el) {
            this.backBtnRef.el.classList.toggle("o_hidden", !inApp);
        }

        if (!this.navRef.el) {
            return;
        }
        // App-owned content: hidden on the dashboard.
        const selectors = [
            ".o_menu_brand",
            ".o_menu_brand_icon",
            ".o_menu_sections",
            ".o_breadcrumb",
        ];
        for (const sel of selectors) {
            this.navRef.el.querySelectorAll(sel).forEach((el) => {
                el.classList.toggle("o_hidden", !inApp);
            });
        }
    }

    /**
     * @override
     * Clicking "all apps" in any sub-menu returns to the dashboard.
     */
    onAllAppsBtnClick() {
        super.onAllAppsBtnClick();
        this.hm.toggle(true);
        this._closeAppMenuSidebar();
    }
}