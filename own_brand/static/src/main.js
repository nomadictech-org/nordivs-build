/** @odoo-module **/

import { startWebClient } from "@web/start";
import { OwnBrandWebClient } from "./webclient/webclient";

/**
 * This file starts the Own Brand web client. In the manifest it REPLACES
 * the community `web/static/src/main.js` so that our custom WebClient
 * (OwnBrandWebClient, which lands on the app grid / home menu) is used
 * instead of the default community one.
 *
 * This reproduces the Enterprise "app dashboard" experience WITHOUT
 * depending on the proprietary `web_enterprise` module.
 */
startWebClient(OwnBrandWebClient);
