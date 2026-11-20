// The assistant's button at the bottom right of every page, with the HumbleBeeAI logo the site's earlier chat
// had: it opens the path panel at its Ask tab. While the panel is open, the tab in it does the same.
import React, { type ReactNode } from "react";
import { useLocation } from "@docusaurus/router";
import useBaseUrl from "@docusaurus/useBaseUrl";
import { usePathApi } from "./api";
import { openAssistant, usePathState } from "./store";
import styles from "./path.module.css";

export default function AskButton(): ReactNode {
  const api = usePathApi();
  const { drawer } = usePathState();
  const { pathname } = useLocation();
  const logo = useBaseUrl("/img/hbai-logo.png");
  // The path and review pages have no panel to open.
  const noPanel = pathname.startsWith("/personal-path") || pathname.startsWith("/review");
  if (!api || drawer || noPanel) return null;
  return (
    <button
      type="button"
      className={styles.askButton}
      onClick={openAssistant}
      aria-label="Ask about your path"
      title="Ask about your path"
    >
      <img src={logo} alt="" />
    </button>
  );
}
