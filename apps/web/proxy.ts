import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";
export default createMiddleware(routing);
export const config = { matcher: ["/", "/en", "/zh-HK", "/methodology", "/en/methodology", "/zh-HK/methodology"] };
