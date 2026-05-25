/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { useService } from "@web/core/utils/hooks";
import { OwnBrandNavBar } from "./navbar/navbar";

/**
 * Custom web client that opens the Home Menu (app grid) as the default
 * landing screen, exactly like the Enterprise app dashboard, but with no
 * dependency on `web_enterprise`.
 */
export class OwnBrandWebClient extends WebClient {
    static components = {
        ...WebClient.components,
        NavBar: OwnBrandNavBar,
    };

    setup() {
        super.setup();
        this.hm = useService("home_menu");
    }

    /**
     * @override
     * Community's WebClient opens the first app. We override it to open
     * the home menu (app grid) instead.
     */
    _loadDefaultApp() {
        return this.hm.toggle(true);
    }
}
