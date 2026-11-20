// The last error message the site showed the learner, so that "why does this not work?" in the chat comes with
// it. Kept in memory for a few minutes only: an old error would mislead the assistant about a new question.
const FRESH_MS = 10 * 60 * 1000;
const MAX_LENGTH = 500;

let last: { text: string; at: number } | null = null;

export function noteError(text: string): void {
  last = { text: text.slice(0, MAX_LENGTH), at: Date.now() };
}

export function recentError(): string | null {
  return last && Date.now() - last.at < FRESH_MS ? last.text : null;
}
