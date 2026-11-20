// Editing keys for the code box, as in a Python editor: Tab and Shift+Tab indent and dedent (several lines at
// once when they are selected), Enter keeps the line's indent and adds one after a colon, Backspace in the
// indent removes one level, Ctrl+/ comments lines in and out. The text changes through the browser's own
// insert command, so Ctrl+Z still undoes each step and React sees an ordinary input.
import type { KeyboardEvent } from "react";

const INDENT = "    ";

// Replaces the text between `start` and `end` and puts the selection where asked.
function replace(box: HTMLTextAreaElement, start: number, end: number, text: string, from: number, to = from) {
  box.setSelectionRange(start, end);
  // execCommand keeps the undo history; where a browser lacks it, setRangeText still edits the text.
  if (!document.execCommand("insertText", false, text)) {
    box.setRangeText(text, start, end, "end");
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }
  box.setSelectionRange(from, to);
}

// The start of the line holding `at`, and the end of the line holding `upTo`.
function lineBounds(value: string, at: number, upTo: number): [number, number] {
  const start = value.lastIndexOf("\n", at - 1) + 1;
  const newline = value.indexOf("\n", upTo);
  return [start, newline === -1 ? value.length : newline];
}

export function onCodeKey(event: KeyboardEvent<HTMLTextAreaElement>): void {
  const box = event.currentTarget;
  const { value, selectionStart: start, selectionEnd: end } = box;

  if (event.key === "Tab") {
    event.preventDefault();
    const several = value.slice(start, end).includes("\n");
    if (!event.shiftKey && !several) {
      replace(box, start, end, INDENT, start + INDENT.length);
      return;
    }
    const [from, to] = lineBounds(value, start, end > start && value[end - 1] === "\n" ? end - 1 : end);
    const lines = value.slice(from, to).split("\n");
    const changed = lines.map((line) =>
      event.shiftKey ? line.replace(new RegExp(`^ {1,${INDENT.length}}`), "") : INDENT + line,
    );
    const text = changed.join("\n");
    const firstShift = changed[0].length - lines[0].length;
    replace(box, from, to, text, Math.max(from, start + firstShift), from + text.length);
    return;
  }

  if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    const before = value.slice(lineStart, start);
    const indent = before.match(/^ */)?.[0] ?? "";
    const opens = /:\s*(#.*)?$/.test(before);
    const text = `\n${indent}${opens ? INDENT : ""}`;
    replace(box, start, end, text, start + text.length);
    return;
  }

  if (event.key === "Backspace" && start === end && start > 0) {
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    const before = value.slice(lineStart, start);
    if (before.length > 0 && /^ +$/.test(before)) {
      event.preventDefault();
      const remove = before.length % INDENT.length || INDENT.length;
      replace(box, start - remove, start, "", start - remove);
    }
    return;
  }

  if (event.key === "/" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    const [from, to] = lineBounds(value, start, end);
    const lines = value.slice(from, to).split("\n");
    const commented = lines.filter((line) => line.trim()).every((line) => /^\s*#/.test(line));
    const text = lines
      .map((line) => {
        if (!line.trim()) return line;
        if (commented) return line.replace(/^(\s*)# ?/, "$1");
        const indent = line.match(/^ */)?.[0] ?? "";
        return `${indent}# ${line.slice(indent.length)}`;
      })
      .join("\n");
    replace(box, from, to, text, from, from + text.length);
  }
}
