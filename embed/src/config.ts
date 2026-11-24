// What the school's script tag says, read once when the script runs:
//
//   <script src="https://api.polarislearning.me/embed/dotpath.js" defer
//           data-site="https://dotpath.polarislearning.me"></script>
//
// data-api      the API; by default the address the script itself was loaded from
// data-site     the course site, for the pages that stay there (public progress, the course team's pages)
// data-content  the element of a lesson page that holds the lesson; by default what the API says for the school
// data-logo     the picture on the assistant's button; by default DotPath's star
// data-pyodide  where Python for coding problems loads from; by default a public CDN

export interface EmbedConfig {
  api: string;
  site: string;
  content: string | null;
  logo: string | null;
  pyodide: string | null;
}

function own(): HTMLScriptElement | null {
  const current = document.currentScript;
  if (current instanceof HTMLScriptElement) return current;
  // `defer` and module scripts have no currentScript by the time they run: find the tag by its address.
  return document.querySelector<HTMLScriptElement>('script[src*="dotpath.js"]');
}

function read(): EmbedConfig {
  const tag = own();
  const data = tag?.dataset ?? {};
  const loadedFrom = tag?.src ? new URL(tag.src, window.location.href).origin : window.location.origin;
  return {
    api: (data.api ?? loadedFrom).replace(/\/$/, ""),
    site: (data.site ?? "https://dotpath.polarislearning.me").replace(/\/$/, ""),
    content: data.content ?? null,
    logo: data.logo ?? null,
    pyodide: data.pyodide ?? null,
  };
}

export const config: EmbedConfig = read();
