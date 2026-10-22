/* Adapted from ccl125/liquid-glass (MIT). See LICENSE.ccl125 in this folder. */
import { liquidGlassMap } from './map.js';

/** Default SVG filter id referenced by liquid-glass.css. */
export const DEFAULT_FILTER_ID = 'liquid-glass';

const CHANNEL_MATRIX = {
  r: '1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0',
  g: '0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0',
  b: '0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0',
};

function buildFilterSvg({ id, scales, saturate }) {
  const [sr, sg, sb] = scales;
  return (
    `<svg aria-hidden="true" style="position:absolute;width:0;height:0;pointer-events:none">` +
    `<defs>` +
    `<filter id="${id}" colorInterpolationFilters="sRGB" x="-20%" y="-80%" width="140%" height="260%">` +
    `<feImage result="map" preserveAspectRatio="none" href="${liquidGlassMap}"/>` +
    // Chromatic dispersion: displace the same map 3 times with slightly
    // different scales, isolate one RGB channel each, then screen-blend.
    `<feDisplacementMap in="SourceGraphic" in2="map" xChannelSelector="R" yChannelSelector="B" result="dispRed" scale="${sr}"/>` +
    `<feColorMatrix in="dispRed" type="matrix" values="${CHANNEL_MATRIX.r}" result="red"/>` +
    `<feDisplacementMap in="SourceGraphic" in2="map" xChannelSelector="R" yChannelSelector="B" result="dispGreen" scale="${sg}"/>` +
    `<feColorMatrix in="dispGreen" type="matrix" values="${CHANNEL_MATRIX.g}" result="green"/>` +
    `<feDisplacementMap in="SourceGraphic" in2="map" xChannelSelector="R" yChannelSelector="B" result="dispBlue" scale="${sb}"/>` +
    `<feColorMatrix in="dispBlue" type="matrix" values="${CHANNEL_MATRIX.b}" result="blue"/>` +
    `<feBlend in="red" in2="green" mode="screen" result="rg"/>` +
    `<feBlend in="rg" in2="blue" mode="screen"/>` +
    `<feColorMatrix type="saturate" values="${saturate}"/>` +
    `</filter>` +
    `</defs>` +
    `</svg>`
  );
}

/**
 * Inject the hidden SVG that defines the liquid glass displacement filter
 * into document.body. Idempotent: if an element with the same id already
 * exists, nothing is added.
 *
 * DOM access happens inside this function only, so importing this module
 * is safe in non-browser environments (SSR, Node).
 *
 * @param {object} [options]
 * @param {string} [options.id='liquid-glass'] Filter id. Must match the id
 *   referenced by your CSS `backdrop-filter: url("#...")`.
 * @param {[number, number, number]} [options.scales=[-127,-124,-121]]
 *   feDisplacementMap scales for the R/G/B passes. Larger absolute values
 *   refract more; the spread between them controls chromatic dispersion.
 *   The default spread (6) keeps text legible; raise it for a stronger
 *   prism look at the cost of RGB ghosting on text.
 * @param {number} [options.saturate=1.35] Final saturation boost.
 * @returns {() => void} cleanup function that removes the injected SVG.
 *   If the filter already existed (injected elsewhere), cleanup is a no-op.
 */
export function injectLiquidGlassFilter({
  id = DEFAULT_FILTER_ID,
  scales = [-127, -124, -121],
  saturate = 1.35,
} = {}) {
  if (typeof document === 'undefined' || !document.body) {
    return () => {};
  }
  if (document.getElementById(id)) {
    return () => {};
  }
  const host = document.createElement('div');
  host.style.display = 'contents';
  host.innerHTML = buildFilterSvg({ id, scales, saturate });
  document.body.appendChild(host);
  return () => {
    host.remove();
  };
}

/**
 * Update an already-injected liquid glass filter in place — useful for live
 * controls. Only the options you pass are updated.
 *
 * DOM access happens inside this function only.
 *
 * @param {object} [options]
 * @param {string} [options.id='liquid-glass'] Filter id to look up.
 * @param {[number, number, number]} [options.scales] New R/G/B displacement
 *   scales, applied to the three feDisplacementMap primitives in order.
 * @param {number} [options.saturate] New value for the trailing
 *   feColorMatrix[type="saturate"] primitive.
 * @returns {boolean} false if no filter with that id exists, true on success.
 */
export function updateLiquidGlassFilter({ id = DEFAULT_FILTER_ID, scales, saturate } = {}) {
  if (typeof document === 'undefined') {
    return false;
  }
  const filter = document.getElementById(id);
  if (!filter) {
    return false;
  }
  if (scales) {
    const primitives = filter.querySelectorAll('feDisplacementMap');
    primitives.forEach((el, i) => {
      if (i < scales.length) el.setAttribute('scale', String(scales[i]));
    });
  }
  if (saturate !== undefined) {
    const el = filter.querySelector('feColorMatrix[type="saturate"]');
    if (el) el.setAttribute('values', String(saturate));
  }
  return true;
}
