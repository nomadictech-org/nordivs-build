/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

/**
 * Applies the per-company dashboard background (gradient / solid / image)
 * configured on the Company form (Dashboard Background page).
 *
 * The ready-to-use CSS value is computed server-side in ir_http.py and exposed
 * through session_info as `session.ownbrand_background.css_bg_image`. Here we
 * write it to a CSS custom property on <html>:
 *
 *     --ownbrand-bg-image
 *
 * home_menu.scss consumes that variable for the dashboard background.
 */
export const ownBrandBackgroundService = {
    start() {
        const bg = session.ownbrand_background;
        if (bg && bg.css_bg_image) {
            document.documentElement.style.setProperty(
                "--ownbrand-bg-image",
                bg.css_bg_image
            );
        }
    },
};

registry.category("services").add("ownbrand_background", ownBrandBackgroundService);
