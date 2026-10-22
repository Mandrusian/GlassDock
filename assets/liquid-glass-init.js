/* Liquid-glass refraction engine adapted from ccl125/liquid-glass (MIT). */
import { injectLiquidGlassFilter } from "./liquid-glass/core.js";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => injectLiquidGlassFilter(), { once: true });
} else {
  injectLiquidGlassFilter();
}
