// Builds dist/dotpath.js: the personal-path components of the course site (site/src/components/personal-path),
// with Docusaurus replaced by src/shims, and their styles inside, for any site to load with one script tag.
//
//   node build.mjs [--site ../site] [--out dist] [--watch]
//
// It uses the course site's own esbuild, React and icons, so the panel is the same code as on the course site.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { themable } from "./themable.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const arg = (name, fallback) => {
  const at = process.argv.indexOf(name);
  return at > 0 ? process.argv[at + 1] : fallback;
};
const site = resolve(here, arg("--site", "../site"));
const out = resolve(here, arg("--out", "dist"));
const modules = join(site, "node_modules");
const require = createRequire(join(modules, "noop.js"));
const esbuild = require("esbuild");

const shims = join(here, "src", "shims", "docusaurus.tsx").replaceAll("\\", "/");
const SHIMS = {
  "@docusaurus/Link": "export { Link as default } from SHIMS;",
  "@docusaurus/useBaseUrl": "export { useBaseUrl as default } from SHIMS;",
  "@docusaurus/BrowserOnly": "export { BrowserOnly as default } from SHIMS;",
  "@docusaurus/useDocusaurusContext": "export { useDocusaurusContext as default } from SHIMS;",
  "@docusaurus/router": "export { useLocation } from SHIMS;",
  "@docusaurus/theme-common": "export { Collapsible } from SHIMS;",
  "@docusaurus/plugin-content-docs/client":
    "export { useAllDocsData, useDoc, useDocsVersion, useActiveVersion } from SHIMS;",
};

const docusaurus = {
  name: "docusaurus-shims",
  setup(build) {
    build.onResolve({ filter: /^@docusaurus\// }, (found) => {
      if (!(found.path in SHIMS)) throw new Error(`No shim for ${found.path} (imported by ${found.importer})`);
      return { path: found.path, namespace: "shim" };
    });
    build.onLoad({ filter: /.*/, namespace: "shim" }, (found) => ({
      contents: SHIMS[found.path].replace("SHIMS", JSON.stringify(shims)),
      loader: "ts",
      resolveDir: here,
    }));
  },
};

// The components' styles, made to follow a school's theme (themable.mjs) before esbuild reads them.
const theming = {
  name: "themable-css",
  setup(build) {
    build.onLoad({ filter: /personal-path[\\/][^\\/]+\.css$/ }, (found) => ({
      contents: themable(readFileSync(found.path, "utf8")),
      loader: found.path.endsWith(".module.css") ? "local-css" : "css",
    }));
  },
};

const options = {
  entryPoints: [join(here, "src", "main.tsx")],
  bundle: true,
  format: "iife",
  target: ["es2020", "chrome100", "firefox100", "safari15"],
  outdir: join(out, "parts"),
  minify: true,
  sourcemap: false,
  legalComments: "none",
  jsx: "automatic",
  nodePaths: [modules],
  alias: {
    "@pp": join(site, "src", "components", "personal-path"),
    react: join(modules, "react"),
    "react-dom": join(modules, "react-dom"),
  },
  define: { "process.env.NODE_ENV": '"production"' },
  logLevel: "warning",
  plugins: [docusaurus, theming],
};

function assemble() {
  const parts = join(out, "parts");
  const base = themable(readFileSync(join(here, "src", "base.css"), "utf8"));
  // The components set their colours on :root; in a shadow root that is :host.
  const components = readFileSync(join(parts, "main.css"), "utf8").replaceAll(":root", ":host");
  const css = `${base}\n${components}`;
  const js = readFileSync(join(parts, "main.js"), "utf8");
  if (!js.includes('"__DOTPATH_CSS__"')) throw new Error("the styles' place is missing from main.js");
  const bundle = js.replace('"__DOTPATH_CSS__"', () => JSON.stringify(css));
  writeFileSync(join(out, "dotpath.js"), `/* DotPath personal path, embeddable. */\n${bundle}`);
  console.log(`dist/dotpath.js: ${(bundle.length / 1024).toFixed(0)} KB (${(css.length / 1024).toFixed(0)} KB of it styles)`);
}

mkdirSync(out, { recursive: true });
if (process.argv.includes("--watch")) {
  const context = await esbuild.context({
    ...options,
    plugins: [
      ...options.plugins,
      { name: "assemble", setup: (build) => build.onEnd((result) => result.errors.length || assemble()) },
    ],
  });
  await context.watch();
  console.log("watching");
} else {
  await esbuild.build(options);
  assemble();
}
