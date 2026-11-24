// Makes the components' styles follow a school's theme without touching them on the course site. The build
// runs it on each component stylesheet before esbuild reads it. Every value it rewrites falls back to the
// original, so with no theme set the widget looks exactly as the course site does.
//
// - Neutral greys (#111, #141414, hsl(0, 0%, 75%) ...) become hsl(<hue> <saturation> <lightness>) with the lightness
//   mapped by two variables, one for text and one for surfaces: the dark theme keeps them, the light theme
//   turns them over (dark surfaces light, light text dark), so pairs that were readable stay readable.
// - Text on the accent (#111 where the background is the accent) follows --dp-on-accent.
// - White at some opacity (borders, hovers) follows --dp-ink; the accent's and amber's tints follow their
//   own colour; shadows scale with --dp-shadow.
// - The few tinted surfaces (gold, blue, green) get variables of their own.
// - Corners scale with --dp-round.

const TEXT_PROPS = new Set(["color", "text-decoration-color", "-webkit-text-fill-color", "caret-color"]);
const TINTS = {
  "#1d1c10": "--dp-tint-gold",
  "#121b22": "--dp-tint-blue",
  "#172029": "--dp-tint-blue-2",
  "#101d14": "--dp-tint-green",
};

function hexToRgb(hex) {
  let h = hex.slice(1);
  if (h.length === 3) h = [...h].map((c) => c + c).join("");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}

// A grey's lightness, mapped for text (f) or for surfaces and lines (b). Surfaces and lines also take the hue
// of the school's background (--dp-h, --dp-s); text stays neutral.
function grey(lightness, kind, alpha) {
  const l = `calc(var(--dp-${kind}a, 0%) + var(--dp-${kind}s, 1) * ${+lightness.toFixed(2)}%)`;
  const hs = kind === "b" ? "var(--dp-h, 0) var(--dp-s, 0%)" : "0 0%";
  return alpha === undefined ? `hsl(${hs} ${l})` : `hsl(${hs} ${l} / ${alpha})`;
}

function rewriteValue(value, prop, onAccent) {
  const kind = TEXT_PROPS.has(prop) ? "f" : "b";
  // Inside var(--x, fallback) the variable decides; leave fallbacks alone.
  const parts = value.split(/(var\([^()]*(?:\([^()]*\)[^()]*)*\))/);
  return parts
    .map((part, index) => {
      if (index % 2 === 1) return part;
      return part
        .replace(/rgba?\(\s*255\s*,\s*255\s*,\s*255\s*,\s*([\d.]+)\s*\)/g, "rgba(var(--dp-ink, 255, 255, 255), $1)")
        .replace(/rgba?\(\s*255\s*,\s*245\s*,\s*0\s*,\s*([\d.]+)\s*\)/g, "rgba(var(--dp-accent-rgb, 255, 245, 0), $1)")
        .replace(/rgba?\(\s*255\s*,\s*185\s*,\s*2\s*,\s*([\d.]+)\s*\)/g, "rgba(var(--dp-amber-rgb, 255, 185, 2), $1)")
        .replace(/rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*([\d.]+)\s*\)/g, "rgba(0, 0, 0, calc($1 * var(--dp-shadow, 1)))")
        .replace(/hsla?\(\s*0\s*,\s*0%\s*,\s*100%\s*,\s*([\d.]+)\s*\)/g, "rgba(var(--dp-ink, 255, 255, 255), $1)")
        .replace(/hsl\(\s*0\s*,\s*0%\s*,\s*([\d.]+)%\s*\)/g, (_, l) => grey(+l, kind))
        .replace(/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b/g, (hex) => {
          const lower = hex.toLowerCase();
          if (TINTS[lower]) return `var(${TINTS[lower]}, ${hex})`;
          const [r, g, b] = hexToRgb(lower);
          if (r !== g || g !== b) return hex; // a brand colour (Google's button): keep
          if (onAccent && kind === "f" && r < 40) return `var(--dp-on-accent, ${hex})`;
          return grey((r / 255) * 100, kind);
        });
    })
    .join("");
}

function rewriteRadius(value) {
  return value.replace(/\b(\d+(?:\.\d+)?)px\b/g, (match, n) =>
    +n >= 2 && +n <= 40 ? `calc(${n}px * var(--dp-round, 1))` : match,
  );
}

export function themable(css) {
  // Innermost blocks only: { declarations } with no nested braces.
  return css.replace(/([^{}]*)\{([^{}]*)\}/g, (block, selector, body) => {
    // Google's button keeps Google's colours (its brand rules ask for a white or a dark button, as given).
    if (/google/i.test(selector)) return `${selector}{${body.replace(/(border-radius\s*:\s*)([^;]+)/g, (_, k, v) => k + rewriteRadius(v))}}`;
    const onAccent = /background(?:-color)?\s*:\s*var\(--(?:pp-gold|accent-gold)\b/.test(body);
    const out = body.replace(/(^|;|\n)(\s*)([-a-zA-Z]+)(\s*:\s*)([^;{}]+)/g, (decl, lead, space, prop, colon, value) => {
      const name = prop.toLowerCase();
      let next = value;
      if (name === "border-radius" || name === "--pp-radius") next = rewriteRadius(value);
      else if (!name.startsWith("--") || /^--(pp|road)-/.test(name)) next = rewriteValue(value, name, onAccent);
      return `${lead}${space}${prop}${colon}${next}`;
    });
    return `${selector}{${out}}`;
  });
}
