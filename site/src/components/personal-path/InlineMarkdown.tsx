import React, { type ReactNode } from "react";
import Link from "@docusaurus/Link";

// Inline Markdown from the curriculum and the checkpoints: **bold**, `code` and [links](...), rendered as
// React elements, never as raw HTML.
const PART = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]*\]\([^)\s]+\))/g;

export function InlineMarkdown({ text }: { text: string }): ReactNode {
  return (
    <>
      {text
        .split(PART)
        .filter(Boolean)
        .map((part, index) => {
          const bold = /^\*\*(.+)\*\*$/.exec(part);
          if (bold) return <strong key={index}>{bold[1]}</strong>;
          const code = /^`(.+)`$/.exec(part);
          if (code) return <code key={index}>{code[1]}</code>;
          const link = /^\[([^\]]*)\]\(([^)\s]+)\)$/.exec(part);
          if (link && /^(https?:\/\/|\/)/.test(link[2])) {
            return (
              <Link key={index} to={link[2]}>
                {link[1]}
              </Link>
            );
          }
          return <React.Fragment key={index}>{part}</React.Fragment>;
        })}
    </>
  );
}
