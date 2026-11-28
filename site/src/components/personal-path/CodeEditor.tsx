// The code box of a coding problem, coloured as in an editor. A textarea with see-through text lies over the same
// code drawn with Prism's Python colours (the VS Code dark theme), so typing, selection, undo and the editing
// keys stay the browser's own. Both layers wrap the same way and the drawn one sets the height.
import React, { type ReactNode } from "react";
import { Highlight, themes } from "prism-react-renderer";
import { onCodeKey } from "./codeKeys";
import styles from "./path.module.css";

export default function CodeEditor({
  value,
  onChange,
  disabled = false,
  label,
}: {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
  label: string;
}): ReactNode {
  return (
    <div className={styles.codeEditor}>
      <Highlight code={value} language="python" theme={themes.vsDark}>
        {({ tokens, getTokenProps }) => (
          <pre className={styles.codeLayer} aria-hidden>
            {/* Only the colours: Prism's class names would pick up the site's own code-block styles. */}
            {tokens.map((line, index) => (
              <span key={index}>
                {line.map((token, at) => (
                  <span key={at} style={getTokenProps({ token }).style}>
                    {token.content}
                  </span>
                ))}
                {"\n"}
              </span>
            ))}
          </pre>
        )}
      </Highlight>
      <textarea
        className={styles.codeInput}
        spellCheck={false}
        autoCapitalize="off"
        autoComplete="off"
        autoCorrect="off"
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onCodeKey}
      />
    </div>
  );
}
