// How the panel looks on this school's site: the theme the API gives with the site (GET /embed/site), or the
// one a designer is trying out right now. It becomes one small stylesheet that every shadow root of the
// widget adopts after the components' own; build.mjs (themable.mjs) made the components' colours follow it.
import { useSyncExternalStore } from "react";

export type Mode = "dark" | "light";
export type Font = "dotpath" | "site" | "system" | "serif";
export type Corners = "sharp" | "default" | "round";

export interface Theme {
  mode: Mode; // follows the background: light text on a dark one, dark text on a light one
  background: string; // #rrggbb, the panel's own background
  accent: string; // #rrggbb
  font: Font;
  corners: Corners;
  logo: string | null;
}

export const DEFAULT_THEME: Theme = {
  mode: "dark",
  background: "#181818",
  accent: "#fff500",
  font: "dotpath",
  corners: "default",
  logo: null,
};
// DotPath's yellow cannot be read on white: on a light background it starts from this instead.
export const LIGHT_ACCENT = "#c2410c";

const ROUND: Record<Corners, number> = { sharp: 0.3, default: 1, round: 1.6 };

// ---------- colour arithmetic ----------

export function rgbOf(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

function luminance(hex: string): number {
  const [r, g, b] = rgbOf(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

// The two backgrounds the themes start from; also what a look saved with only its mode means.
export const SURFACE: Record<Mode, string> = { dark: "#181818", light: "#ffffff" };

// Light text on a dark background, dark text on a light one.
export function modeOf(background: string): Mode {
  return contrast(background, "#000000") > contrast(background, "#ffffff") ? "light" : "dark";
}

function hslOf(hex: string): [number, number, number] {
  const [r, g, b] = rgbOf(hex).map((v) => v / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return [0, 0, l * 100];
  const s = d / (1 - Math.abs(2 * l - 1));
  const h = max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s * 100, l * 100];
}

// Text on a button of the accent colour: whichever of near-black and white reads better.
function onAccent(accent: string): string {
  return contrast(accent, "#111111") >= contrast(accent, "#ffffff") ? "#111111" : "#ffffff";
}

export const isHex = (value: string) => /^#[0-9a-fA-F]{6}$/.test(value);

// ---------- fonts ----------

const DOTPATH_BODY = '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const DOTPATH_HEAD = '"Space Grotesk", "Inter", system-ui, sans-serif';
const SYSTEM = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
const SERIF = 'Georgia, "Iowan Old Style", "Times New Roman", serif';

// The school's own fonts, as its page has them (its body text and its first heading).
export function siteFonts(): [string, string] {
  const clean = (value: string) => value.replace(/[;{}<>\\]/g, "").trim();
  const body = clean(getComputedStyle(document.body).fontFamily) || SYSTEM;
  const heading = document.querySelector("h1, h2");
  return [body, heading ? clean(getComputedStyle(heading).fontFamily) || body : body];
}

function fontsOf(font: Font): [string, string] {
  switch (font) {
    case "site":
      return siteFonts();
    case "system":
      return [SYSTEM, SYSTEM];
    case "serif":
      return [SERIF, SERIF];
    default:
      return [DOTPATH_BODY, DOTPATH_HEAD];
  }
}

// ---------- the stylesheet ----------

// The lightness of the components' main surface (#181818): the background colour takes its place.
const BASE_SURFACE = 9.41;

export function themeCss(theme: Theme): string {
  const accent = isHex(theme.accent) ? theme.accent.toLowerCase() : DEFAULT_THEME.accent;
  const background = isHex(theme.background) ? theme.background.toLowerCase() : DEFAULT_THEME.background;
  const mode = modeOf(background);
  const [r, g, b] = rgbOf(accent);
  const [body, heading] = fontsOf(theme.font);
  const rules = [
    `--accent-gold: ${accent};`,
    `--accent-gold-light: color-mix(in srgb, ${accent} 78%, white);`,
    `--dp-accent-rgb: ${r}, ${g}, ${b};`,
    `--dp-on-accent: ${onAccent(accent)};`,
    `--dp-round: ${ROUND[theme.corners] ?? 1};`,
    `--ifm-font-family-base: ${body};`,
    `--ifm-heading-font-family: ${heading};`,
  ];
  if (mode === "light") {
    rules.push(
      "--ifm-font-color-base: #1c1c1a;",
      "--ifm-font-color-secondary: #5c5b57;",
      "--ifm-menu-color-active: #1c1c1a;",
      "--ifm-background-color: #ffffff;",
      "--pp-surface: #ffffff;",
      "--pp-raised: #f5f4f0;",
      "--pp-hover: #ecebe6;",
      "--pp-muted: #62615c;",
      "--pp-blue: hsl(206, 80%, 36%);",
      "--pp-blue-soft: hsla(206, 80%, 45%, 0.1);",
      "--pp-green: hsl(142, 65%, 27%);",
      "--pp-green-soft: hsla(142, 60%, 35%, 0.12);",
      "--pp-red: hsl(0, 70%, 42%);",
      "--pp-red-soft: hsla(0, 70%, 50%, 0.1);",
      "--accent-amber: #b45309;",
      "--dp-amber-rgb: 180, 83, 9;",
      "--dp-ink: 0, 0, 0;",
      "--dp-shadow: 0.3;",
      // Greys turn over: text from light to dark, surfaces and lines from dark to light (more gently).
      "--dp-fa: 100%;",
      "--dp-fs: -1;",
      "--dp-ba: 100%;",
      "--dp-bs: -0.45;",
      `--dp-tint-gold: color-mix(in srgb, ${accent} 12%, ${background});`,
      `--dp-tint-blue: color-mix(in srgb, #eaf2f9 85%, ${background});`,
      `--dp-tint-blue-2: color-mix(in srgb, #e2ecf6 85%, ${background});`,
      `--dp-tint-green: color-mix(in srgb, #e8f5ec 85%, ${background});`,
    );
  } else if (accent !== DEFAULT_THEME.accent || background !== DEFAULT_THEME.background) {
    rules.push(`--dp-tint-gold: color-mix(in srgb, ${accent} 9%, ${background});`);
  }
  // A background other than the two the themes start from: surfaces, lines and hovers take its colour.
  if (background !== SURFACE[mode]) {
    const [h, s, l] = hslOf(background);
    rules.push(
      `--dp-h: ${h.toFixed(1)};`,
      `--dp-s: ${(s * 0.6).toFixed(1)}%;`,
      mode === "light"
        ? `--dp-ba: ${Math.min(100, l + 0.45 * BASE_SURFACE).toFixed(2)}%;`
        : `--dp-ba: ${(l - BASE_SURFACE).toFixed(2)}%;`,
      `--ifm-background-color: ${background};`,
      `--pp-surface: ${background};`,
      `--pp-raised: color-mix(in srgb, ${background} ${mode === "light" ? "96%, black" : "94%, white"});`,
      `--pp-hover: color-mix(in srgb, ${background} ${mode === "light" ? "92%, black" : "89%, white"});`,
    );
  }
  return `:host {\n  ${rules.join("\n  ")}\n}\n:host { color-scheme: ${mode}; }`;
}

// ---------- the current theme ----------

let current: Theme = DEFAULT_THEME;
const listeners = new Set<() => void>();
const sheets: CSSStyleSheet[] = [];
const styles: HTMLStyleElement[] = [];

export function getTheme(): Theme {
  return current;
}

export function setTheme(theme: Partial<Theme>): void {
  // A look saved before the background could be any colour has only its mode.
  const background = theme.background && isHex(theme.background) ? theme.background : SURFACE[theme.mode ?? "dark"];
  current = { ...DEFAULT_THEME, ...theme, background, mode: modeOf(background) };
  const css = themeCss(current);
  for (const sheet of sheets) sheet.replaceSync(css);
  for (const style of styles) style.textContent = css;
  listeners.forEach((listener) => listener());
}

// The stylesheet a new shadow root adopts; or, where adopting is not supported, a <style> to append.
let shared: CSSStyleSheet | null = null;
export function themeSheet(): CSSStyleSheet {
  if (!shared) {
    shared = new CSSStyleSheet();
    shared.replaceSync(themeCss(current));
    sheets.push(shared);
  }
  return shared;
}

export function themeStyle(): HTMLStyleElement {
  const style = document.createElement("style");
  style.textContent = themeCss(current);
  styles.push(style);
  return style;
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}
