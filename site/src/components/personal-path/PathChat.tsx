// The assistant in the path panel: the learner asks about their path or the module they are reading. The
// API answers from the stored path; the conversation stays on this page until the learner reloads it.
import React, { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import Link from "@docusaurus/Link";
import { ArrowUp, RotateCcw, Sparkles } from "lucide-react";
import { message, type ChatTurn, type PathApi } from "./api";
import { InlineMarkdown } from "./InlineMarkdown";
import { nextUp, statusOf, type LearningPath, type PathItem } from "./model";
import { currentOpenProblem, handleSignedOut, openAuth, takePendingQuestion, usePathState } from "./store";
import { useModulePages } from "./useModulePages";
import { recentError } from "./pageErrors";
import { Spinner } from "./ui";
import styles from "./chat.module.css";

interface Message extends ChatTurn {
  modules?: { id: string; title: string }[];
}

const MAX_QUESTION = 1000;

// A few questions to start from, picked from where the learner is.
function suggestions(path: LearningPath, page: PathItem | undefined): string[] {
  const asked: string[] = [];
  if (page) asked.push(`Explain the main ideas of ${page.module.title} simply.`);
  const failed = path.items.find((item) => statusOf(path, item) === "failed");
  if (failed) asked.push(`I failed the ${failed.module.title} checkpoint. What should I review?`);
  const next = nextUp(path);
  if (next) asked.push(`Why is ${next.module.title} next in my path?`);
  const skipped = path.items.find((item) => item.choice === "skip");
  if (skipped) asked.push(`Why do I skip ${skipped.module.title}?`);
  asked.push("How much is left, and how long will it take?");
  return asked.slice(0, 3);
}

// Short Markdown from the model: paragraphs and "- " lists, with inline bold, code and links.
// The topic of the module page the learner is reading: the last second-level heading above the middle of the
// window. So "quiz me" or "explain this" is about what is on their screen, not the whole module. Third-level
// headings repeat in every topic ("Learning resources", "Practice"), so they would say little.
function sectionInView(): string | null {
  const headings = Array.from(document.querySelectorAll<HTMLElement>("article h2"));
  const middle = window.innerHeight / 2;
  let found: HTMLElement | null = null;
  for (const heading of headings) {
    if (heading.getBoundingClientRect().top <= middle) found = heading;
    else break;
  }
  const text = found?.textContent?.replace(/\u200b/g, "").trim();
  return text ? text.slice(0, 200) : null;
}

// A reply with code blocks: the parts between ``` fences are code, shown as written, with every space; the
// rest is prose. An answer cut off inside a block still shows the code it has.
export function Reply({ text }: { text: string }): ReactNode {
  const parts = text.split(/```[^\n`]*\n?/);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <pre key={index} className={styles.codeBlock}>
            <code>{part.replace(/\n$/, "")}</code>
          </pre>
        ) : part.trim() ? (
          <Prose key={index} text={part} />
        ) : null,
      )}
    </>
  );
}

// Prose as paragraphs and lists. Within a block, lines in a row that start with "1." make a numbered list
// (keeping the model's numbers), lines that start with "-" a bulleted one, the rest a paragraph.
function Prose({ text }: { text: string }): ReactNode {
  const NUMBERED = /^\s*\d+\.\s+/;
  const BULLET = /^\s*[-*]\s+/;
  const parts: ReactNode[] = [];
  text
    .trim()
    .split(/\n\s*\n/)
    .forEach((block, blockIndex) => {
      // A Markdown heading ("## What to write") reads as a bold line; code blocks never reach here.
      const lines = block
        .split("\n")
        .filter((line) => line.trim())
        .map((line) => line.replace(/^#{1,6}\s+(.+)$/, "**$1**"));
      let index = 0;
      while (index < lines.length) {
        const kind = NUMBERED.test(lines[index]) ? "ol" : BULLET.test(lines[index]) ? "ul" : "p";
        const run: string[] = [];
        while (index < lines.length) {
          const line = lines[index];
          const lineKind = NUMBERED.test(line) ? "ol" : BULLET.test(line) ? "ul" : "p";
          if (lineKind !== kind) break;
          run.push(line);
          index++;
        }
        const key = `${blockIndex}-${index}`;
        if (kind === "p")
          parts.push(
            <p key={key}>
              {run.map((line, item) => (
                <React.Fragment key={item}>
                  {item > 0 && <br />}
                  <InlineMarkdown text={line} />
                </React.Fragment>
              ))}
            </p>,
          );
        else {
          const items = run.map((line, item) => (
            <li key={item}>
              <InlineMarkdown text={line.replace(kind === "ol" ? NUMBERED : BULLET, "")} />
            </li>
          ));
          parts.push(
            kind === "ol" ? (
              <ol key={key} start={Number(run[0].trim().split(".")[0])}>
                {items}
              </ol>
            ) : (
              <ul key={key}>{items}</ul>
            ),
          );
        }
      }
    });
  return <>{parts}</>;
}

export default function PathChat({
  api,
  path,
  pageModuleId,
}: {
  api: PathApi;
  path: LearningPath | null;
  pageModuleId: string | undefined;
}): ReactNode {
  const { account, pendingQuestion } = usePathState();
  const pageOf = useModulePages(path?.curriculum_site_version ?? null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  // Another learner on this browser starts with an empty conversation.
  useEffect(() => {
    setMessages([]);
    setError(null);
  }, [account?.email]);

  // After each message, the panel scrolls so it is in view: an answer from its first line, under the bar
  // above the conversation; anything shorter to the bottom. The composer is sticky at the bottom of the
  // panel, so scrolling an element "into view" alone would leave it under the composer.
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const bottom = end.current;
      const panel = bottom?.closest<HTMLElement>("[role=tabpanel]");
      if (!bottom || !panel) return;
      const said = panel.querySelectorAll<HTMLElement>("[data-speaker]");
      const last = said[said.length - 1];
      const bar = panel.querySelector<HTMLElement>(`.${styles.chatTop}`)?.offsetHeight ?? 0;
      const composer = panel.querySelector<HTMLElement>(`.${styles.composer}`)?.offsetHeight ?? 0;
      const visible = panel.clientHeight - bar - composer;
      if (last && last.dataset.speaker === "assistant" && last.offsetHeight > visible - 24) {
        const top = last.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop;
        panel.scrollTo({ top: top - bar - 12, behavior: "smooth" });
      } else {
        panel.scrollTo({ top: panel.scrollHeight, behavior: "smooth" });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [messages, busy]);

  useEffect(() => {
    const box = input.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 160)}px`;
  }, [draft]);

  // A question put in from elsewhere on the page, such as the coding problem's "Ask the assistant": it lands in
  // the box, ready to send or change, and the box takes the focus.
  useEffect(() => {
    if (!pendingQuestion) return;
    const question = takePendingQuestion();
    if (!question) return;
    setDraft(question.text);
    requestAnimationFrame(() => {
      const box = input.current;
      if (!box) return;
      box.focus();
      box.setSelectionRange(box.value.length, box.value.length);
    });
  }, [pendingQuestion]);

  if (!account) {
    return (
      <div className={styles.empty}>
        <Sparkles size={22} aria-hidden />
        <strong>Ask about your path</strong>
        <p>Create a free account to keep your path; then ask why a module is in it or what a page means.</p>
        <button type="button" className={styles.primary} onClick={() => openAuth("sign-up")}>
          Create account
        </button>
      </div>
    );
  }
  if (!path) {
    return (
      <div className={styles.empty}>
        <Sparkles size={22} aria-hidden />
        <strong>Plan your path first</strong>
        <p>Answer a few questions in the Path tab; then ask about the path you get.</p>
      </div>
    );
  }

  const page = path.items.find((item) => item.module.id === pageModuleId);

  async function ask(
    question: string,
    attached: { code: string; error: string } | null = null,
    moduleId: string | null = page?.module.id ?? null,
  ) {
    const text = question.trim();
    if (!text || busy) return;
    const history = messages.slice(-8).map(({ speaker, text: said }) => ({
      speaker,
      text: said.slice(0, 2000),
    }));
    setMessages((current) => [...current, { speaker: "learner", text }]);
    setDraft("");
    setBusy(true);
    setError(null);
    try {
      // On a module page with its coding problem open, the code goes with every question, so "why does my
      // code fail" works without the button.
      const open = currentOpenProblem();
      const withCode =
        attached ??
        (open && open.moduleId === moduleId && open.code.trim()
          ? { code: open.code.slice(0, 6000), error: open.lastRun ?? "The tests have not been run yet." }
          : null);
      const answer = await api.chat(
        text,
        history,
        moduleId,
        page && !attached ? sectionInView() : null,
        withCode,
        recentError(),
      );
      setMessages((current) => [
        ...current,
        { speaker: "assistant", text: answer.reply, modules: answer.modules },
      ]);
    } catch (reason) {
      if (!handleSignedOut(reason)) setError(message(reason));
      // The question goes back into the box, so that trying again does not mean typing it again.
      setMessages((current) => current.slice(0, -1));
      if (!attached) setDraft(text);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  return (
    <div className={styles.chat}>
      {messages.length > 0 && (
        <div className={styles.chatTop}>
          <span>Conversation about your path</span>
          <button type="button" onClick={() => setMessages([])} disabled={busy} title="Clear this conversation and start over">
            <RotateCcw size={14} aria-hidden /> New chat
          </button>
        </div>
      )}
      <div className={styles.log} aria-live="polite">
        {messages.length === 0 && (
          <div className={styles.intro}>
            <Sparkles size={20} aria-hidden />
            <p>
              Ask why a module is in your path, what to do next, or what something on
              {page ? (
                <>
                  {" "}
                  the <strong>{page.module.title}</strong> page
                </>
              ) : (
                " a module page"
              )}{" "}
              means.
            </p>
            <div className={styles.suggestions}>
              {suggestions(path, page).map((question) => (
                <button key={question} type="button" onClick={() => void ask(question)} disabled={busy}>
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((said, index) => (
          <div key={index} className={styles.message} data-speaker={said.speaker}>
            {said.speaker === "assistant" ? <Reply text={said.text} /> : <p>{said.text}</p>}
            {said.modules && said.modules.length > 0 && (
              <div className={styles.links}>
                {said.modules.map((module) => {
                  const href = pageOf(module.id);
                  return href ? (
                    <Link key={module.id} to={href}>
                      {module.title}
                    </Link>
                  ) : null;
                })}
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div className={styles.message} data-speaker="assistant" aria-label="The assistant is answering">
            <span className={styles.typing}>
              <span />
              <span />
              <span />
            </span>
          </div>
        )}
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <div ref={end} />
      </div>
      <form className={styles.composer} onSubmit={submit}>
        {page && <span className={styles.context}>About this page: {page.module.title}</span>}
        <div className={styles.box}>
          <textarea
            ref={input}
            rows={1}
            value={draft}
            maxLength={MAX_QUESTION}
            placeholder="Ask about your path or this page"
            aria-label="Your question"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void ask(draft);
              }
            }}
          />
          <button type="submit" className={styles.send} disabled={busy || !draft.trim()} aria-label="Send">
            {busy ? <Spinner /> : <ArrowUp size={18} aria-hidden />}
          </button>
        </div>
        <div className={styles.footer}>
          <span>The assistant can make mistakes. Check its answers against your path.</span>
        </div>
      </form>
    </div>
  );
}
