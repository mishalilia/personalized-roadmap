// The window where the school's people change how the panel looks on their site. Every change shows at once
// on the real page behind it (the panel opens beside it, the lesson's blocks are on the page); "Save" makes
// it what every visitor gets. Only accounts the API names as the site's designers see it.
import React, { useEffect, useState, type ReactNode } from "react";
import { setDrawer } from "@pp/store";
import { embedding } from "@pp/api";
import { config } from "./config";
import {
  DEFAULT_THEME,
  LIGHT_ACCENT,
  SURFACE,
  contrast,
  getTheme,
  isHex,
  nearProveBlue,
  setTheme,
  siteFonts,
  type Corners,
  type Font,
  type Mode,
  type Theme,
} from "./theme";

const SWATCHES = ["#fff500", "#ff7a1a", "#c2410c", "#2f6fed", "#12a37a", "#d6336c", "#7c3aed", "#111111"];
const FONTS: { value: Font; label: string; family: string }[] = [
  { value: "dotpath", label: "DotPath", family: '"Space Grotesk", "Inter", sans-serif' },
  { value: "site", label: "The site's", family: "inherit" },
  { value: "system", label: "System", family: "system-ui, sans-serif" },
  { value: "serif", label: "Serif", family: "Georgia, serif" },
];
const CORNERS: { value: Corners; label: string; radius: string }[] = [
  { value: "sharp", label: "Sharp", radius: "2px" },
  { value: "default", label: "Soft", radius: "8px" },
  { value: "round", label: "Round", radius: "14px" },
];

async function save(theme: Theme): Promise<Theme> {
  const headers: Record<string, string> = { "Content-Type": "application/json", "X-DotPath-Embed": "1" };
  const token = embedding.token();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${config.api}/embed/theme`, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify(theme),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(
      response.status === 403
        ? "This account may not change the panel's look on this site."
        : response.status === 422
          ? "The API refused one of these values. Check the logo's address."
          : typeof body?.detail === "string"
            ? body.detail
            : `The API answered ${response.status}.`,
    );
  }
  return (await response.json()) as Theme;
}

export default function Designer({ onClose }: { onClose: () => void }): ReactNode {
  // What visitors get now, and what this window shows.
  const [saved, setSaved] = useState<Theme>(getTheme);
  const [draft, setDraft] = useState<Theme>(getTheme);
  const [hex, setHex] = useState(draft.accent);
  const [logo, setLogo] = useState(draft.logo ?? "");
  const [status, setStatus] = useState<{ kind: "ok" | "error" | "busy"; text: string } | null>(null);

  useEffect(() => setDrawer(true), []);
  useEffect(() => setTheme(draft), [draft]);

  const change = (next: Partial<Theme>) => {
    setStatus(null);
    setDraft((before) => {
      const theme = { ...before, ...next };
      // DotPath's yellow cannot be read on white: a light theme starts from a darker accent.
      if (next.mode === "light" && before.accent.toLowerCase() === DEFAULT_THEME.accent) theme.accent = LIGHT_ACCENT;
      if (next.mode === "dark" && before.accent.toLowerCase() === LIGHT_ACCENT) theme.accent = DEFAULT_THEME.accent;
      if (theme.accent !== before.accent) setHex(theme.accent);
      return theme;
    });
  };

  const changed = JSON.stringify(draft) !== JSON.stringify(saved);
  const readable = contrast(draft.accent, SURFACE[draft.mode]);
  const logoOk = !logo.trim() || /^https?:\/\/[^\s"'()<>]+$/.test(logo.trim());

  function close() {
    setTheme(saved);
    onClose();
  }

  async function keep() {
    setStatus({ kind: "busy", text: "Saving…" });
    try {
      const theme = await save(draft);
      setSaved(theme);
      setStatus({ kind: "ok", text: "Saved. Every visitor of this site gets this look now." });
    } catch (reason) {
      setStatus({ kind: "error", text: reason instanceof Error ? reason.message : String(reason) });
    }
  }

  return (
    <section className="designer" role="dialog" aria-modal="false" aria-labelledby="designer-title">
      <header>
        <div>
          <h2 id="designer-title">Panel design</h2>
          <p>Changes show on this page at once. Visitors see them after you save.</p>
        </div>
        <button type="button" className="close" aria-label="Close without saving" onClick={close}>
          ×
        </button>
      </header>

      <fieldset>
        <legend>Theme</legend>
        <div className="segmented">
          {(["dark", "light"] as Mode[]).map((mode) => (
            <button key={mode} type="button" aria-pressed={draft.mode === mode} onClick={() => change({ mode })}>
              <span className={`chip ${mode}`} aria-hidden /> {mode === "dark" ? "Dark" : "Light"}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Accent colour</legend>
        <div className="swatches">
          {SWATCHES.map((colour) => (
            <button
              key={colour}
              type="button"
              className="swatch"
              style={{ background: colour }}
              aria-label={colour}
              aria-pressed={draft.accent.toLowerCase() === colour}
              onClick={() => change({ accent: colour })}
            />
          ))}
        </div>
        <div className="row">
          <input
            type="color"
            aria-label="Any colour"
            value={draft.accent}
            onChange={(event) => change({ accent: event.target.value })}
          />
          <input
            type="text"
            className="hex"
            aria-label="Colour code"
            spellCheck={false}
            value={hex}
            onChange={(event) => {
              const value = event.target.value.trim();
              setHex(value);
              if (isHex(value)) change({ accent: value.toLowerCase() });
            }}
          />
        </div>
        {readable < 3 && (
          <p className="warn">
            Text in this colour is hard to read on the {draft.mode} panel ({readable.toFixed(1)}:1, 3:1 at least).
            {draft.mode === "light" ? " Pick a darker one." : " Pick a lighter one."}
          </p>
        )}
        {nearProveBlue(draft.accent) && (
          <p className="warn">
            Close to the blue of modules to prove: on the path and the map they will look like modules to study.
          </p>
        )}
      </fieldset>

      <fieldset>
        <legend>Font</legend>
        <div className="segmented four">
          {FONTS.map((font) => (
            <button
              key={font.value}
              type="button"
              aria-pressed={draft.font === font.value}
              style={{ fontFamily: font.value === "site" ? siteFonts()[0] : font.family }}
              onClick={() => change({ font: font.value })}
            >
              {font.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Corners</legend>
        <div className="segmented">
          {CORNERS.map((corner) => (
            <button
              key={corner.value}
              type="button"
              aria-pressed={draft.corners === corner.value}
              onClick={() => change({ corners: corner.value })}
            >
              <span className="corner" style={{ borderTopLeftRadius: corner.radius }} aria-hidden /> {corner.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Logo on the assistant's button</legend>
        <div className="row">
          <input
            type="url"
            className="logo"
            placeholder="https://… (empty: DotPath's star)"
            value={logo}
            aria-invalid={!logoOk}
            onChange={(event) => {
              const value = event.target.value;
              setLogo(value);
              const trimmed = value.trim();
              if (!trimmed) change({ logo: null });
              else if (/^https?:\/\/[^\s"'()<>]+$/.test(trimmed)) change({ logo: trimmed });
            }}
          />
          {draft.logo && <img src={draft.logo} alt="" className="logoPreview" />}
        </div>
        {!logoOk && <p className="warn">An address starting with https://</p>}
      </fieldset>

      <footer>
        <button
          type="button"
          className="link"
          onClick={() => {
            setLogo("");
            setHex(DEFAULT_THEME.accent);
            setStatus(null);
            setDraft(DEFAULT_THEME);
          }}
        >
          DotPath's look
        </button>
        <span className="spacer" />
        <button type="button" className="ghost" onClick={close}>
          {changed ? "Cancel" : "Close"}
        </button>
        <button
          type="button"
          className="primary"
          disabled={!changed || !logoOk || status?.kind === "busy"}
          onClick={() => void keep()}
        >
          Save
        </button>
      </footer>
      {status && (
        <p className={`status ${status.kind}`} role="status">
          {status.text}
        </p>
      )}
    </section>
  );
}

// Its own look, the same on every school and whatever theme is being tried, so it stays readable.
export const DESIGNER_CSS = `
:host { all: initial; position: fixed; left: 16px; bottom: 16px; z-index: 2147483001; }
.designer {
  box-sizing: border-box; width: 340px; max-height: calc(100vh - 32px); overflow: auto;
  padding: 18px 18px 14px; border-radius: 14px; background: #fff; color: #1c1c1a;
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  box-shadow: 0 18px 50px rgba(0,0,0,.28), 0 0 0 1px rgba(0,0,0,.08);
}
.designer *, .designer *::before, .designer *::after { box-sizing: border-box; }
header { display: flex; gap: 12px; align-items: flex-start; margin-bottom: 6px; }
header > div { flex: 1; }
h2 { margin: 0; font-size: 17px; font-weight: 650; }
header p { margin: 3px 0 0; color: #66655f; font-size: 12.5px; }
.close { border: 0; background: none; font-size: 22px; line-height: 1; color: #66655f; cursor: pointer; padding: 2px 6px; border-radius: 6px; }
.close:hover { background: #f0efeb; color: #1c1c1a; }
fieldset { border: 0; margin: 14px 0 0; padding: 0; min-width: 0; }
legend { padding: 0; margin-bottom: 7px; font-size: 12px; font-weight: 600; letter-spacing: .03em; text-transform: uppercase; color: #66655f; }
button { font: inherit; color: inherit; cursor: pointer; }
.segmented { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 4px; padding: 3px; border-radius: 10px; background: #f0efeb; }
.segmented button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 0; padding: 7px 6px; border-radius: 7px; background: none; white-space: nowrap; }
.segmented button[aria-pressed="true"] { background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.15); font-weight: 600; }
.chip { width: 14px; height: 14px; border-radius: 4px; border: 1px solid rgba(0,0,0,.2); }
.chip.dark { background: #181818; } .chip.light { background: #fff; }
.corner { width: 14px; height: 14px; border-top: 2px solid currentColor; border-left: 2px solid currentColor; }
.swatches { display: flex; flex-wrap: wrap; gap: 7px; }
.swatch { width: 28px; height: 28px; border-radius: 50%; border: 1px solid rgba(0,0,0,.15); padding: 0; }
.swatch[aria-pressed="true"] { box-shadow: 0 0 0 2px #fff, 0 0 0 4px #1c1c1a; }
.row { display: flex; gap: 8px; align-items: center; margin-top: 9px; }
input[type="color"] { width: 38px; height: 34px; padding: 2px; border: 1px solid #d6d4cd; border-radius: 8px; background: #fff; cursor: pointer; }
input[type="text"], input[type="url"] { flex: 1; min-width: 0; height: 34px; padding: 0 10px; border: 1px solid #d6d4cd; border-radius: 8px; font: inherit; color: inherit; background: #fff; }
.hex { font-family: ui-monospace, Menlo, Consolas, monospace !important; text-transform: lowercase; }
input:focus-visible, button:focus-visible { outline: 2px solid #2f6fed; outline-offset: 1px; }
input[aria-invalid="true"] { border-color: #c0392b; }
.logoPreview { width: 34px; height: 34px; object-fit: contain; border-radius: 8px; border: 1px solid #d6d4cd; }
.warn { margin: 8px 0 0; color: #a1461a; font-size: 12.5px; }
footer { display: flex; align-items: center; gap: 8px; margin-top: 18px; padding-top: 12px; border-top: 1px solid #ecebe6; }
.spacer { flex: 1; }
.link { border: 0; background: none; padding: 0; color: #66655f; text-decoration: underline; font-size: 12.5px; }
.ghost, .primary { border-radius: 8px; padding: 7px 14px; font-weight: 600; }
.ghost { border: 1px solid #d6d4cd; background: #fff; }
.primary { border: 1px solid #1c1c1a; background: #1c1c1a; color: #fff; }
.primary:disabled { opacity: .4; cursor: default; }
.status { margin: 10px 0 0; font-size: 12.5px; }
.status.ok { color: #1d7a3e; } .status.error { color: #b3261e; } .status.busy { color: #66655f; }
@media (max-width: 600px) {
  :host { left: 8px; right: 8px; bottom: 8px; }
  .designer { width: 100%; max-height: 60vh; }
}
`;
