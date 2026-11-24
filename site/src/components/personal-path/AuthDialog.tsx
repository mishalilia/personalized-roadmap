// Sign up or sign in, in a dialog over whatever page the learner is on. A draft path planned before
// signing in becomes the account's path.
import React, { useEffect, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { embedding, message, signInWithGoogleWindow, usePathApi } from "./api";
import { applySession, closeAuth, openAuth, startSession, usePathState, type AuthMode } from "./store";
import { Spinner } from "./ui";
import styles from "./path.module.css";

const MIN_PASSWORD = 6;

export default function AuthDialog(): ReactNode {
  const api = usePathApi();
  const { auth, draftId, path } = usePathState();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [google, setGoogle] = useState(false);
  const dialog = useRef<HTMLDivElement>(null);
  const mode: AuthMode = auth?.mode ?? "sign-up";

  // Mounted on every page (theme/Root.tsx), so the session starts wherever the learner arrives.
  useEffect(() => {
    if (!api) return;
    void startSession(api);
    api
      .providers()
      .then((found) => setGoogle(found.google))
      .catch(() => setGoogle(false));
  }, [api]);

  useEffect(() => {
    if (!auth) return;
    setError(null);
    setPassword("");
    dialog.current?.querySelector<HTMLInputElement>("input")?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && closeAuth();
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [auth?.mode, auth !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!auth || !api) return null;

  async function submit() {
    if (!api) return;
    setBusy(true);
    setError(null);
    try {
      const session =
        mode === "sign-up"
          ? await api.signUp(email, password, draftId)
          : await api.signIn(email, password, draftId);
      applySession(session);
      setEmail("");
      setPassword("");
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy(false);
    }
  }

  const keepsDraft = draftId !== null && path !== null;
  const title = mode === "sign-up" ? "Create your account" : "Welcome back";

  return (
    <div className={styles.overlay} onMouseDown={(event) => event.target === event.currentTarget && closeAuth()}>
      <div
        ref={dialog}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
      >
        <button type="button" className={styles.iconButton} onClick={closeAuth} aria-label="Close">
          <X size={18} />
        </button>
        <h2 id="auth-title">{title}</h2>
        <p className={styles.muted}>
          {auth.reason ??
            (mode === "sign-up"
              ? "Save your personal path and track your progress through the course."
              : "Sign in to continue your personal path.")}
        </p>
        {google && (
          <>
            <a
              className={styles.googleButton}
              href={api.googleSignIn(window.location.href.split("#")[0], draftId)}
              onClick={(event) => {
                // Embedded in another site: Google in a window of its own (api.ts).
                if (!embedding.on) return;
                event.preventDefault();
                setBusy(true);
                setError(null);
                signInWithGoogleWindow(api, draftId)
                  .then(applySession, (reason: unknown) => setError(message(reason)))
                  .finally(() => setBusy(false));
              }}
            >
              <GoogleLogo />
              Continue with Google
            </a>
            <div className={styles.divider}>
              <span>or with your email</span>
            </div>
          </>
        )}
        {keepsDraft && (
          <p className={styles.note}>
            The path you just planned will be saved to your account
            {mode === "sign-in" && ", replacing any path the account already has"}.
          </p>
        )}
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label className={styles.field}>
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className={styles.field}>
            <span>Password</span>
            <input
              type="password"
              autoComplete={mode === "sign-up" ? "new-password" : "current-password"}
              required
              minLength={mode === "sign-up" ? MIN_PASSWORD : undefined}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {mode === "sign-up" && <small>At least {MIN_PASSWORD} characters.</small>}
          </label>
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          <button type="submit" className={styles.primary} disabled={busy}>
            {busy && <Spinner />}
            {mode === "sign-up" ? "Create account" : "Sign in"}
          </button>
        </form>
        <p className={styles.switch}>
          {mode === "sign-in" && google && (
            <>
              Signed up with Google? Use the button above.
              <br />
            </>
          )}
          {mode === "sign-up" ? "Already have an account?" : "New here?"}{" "}
          <button
            type="button"
            className={styles.link}
            onClick={() => openAuth(mode === "sign-up" ? "sign-in" : "sign-up", auth.reason)}
          >
            {mode === "sign-up" ? "Sign in" : "Create an account"}
          </button>
        </p>
        {mode === "sign-up" && (
          <p className={styles.fine}>
            Your account keeps your email, your path and your onboarding answers, nothing else. You can
            delete it, with everything in it, from the account menu at any time. With Google, we receive only
            your email address.
          </p>
        )}
      </div>
    </div>
  );
}

// Google's "G", as its sign-in branding guidelines ask.
function GoogleLogo(): ReactNode {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}
