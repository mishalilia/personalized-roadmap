// The learner's account, in the path panel: their email, signing out, deleting it all.
import React, { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, BarChart3, ClipboardCheck, LogOut, Trash2 } from "lucide-react";
import { message, usePathApi } from "./api";
import { applySession } from "./store";
import styles from "./path.module.css";

export default function AccountMenu({
  email,
  hasPassword,
  reviewer = false,
}: {
  email: string;
  hasPassword: boolean;
  reviewer?: boolean;
}): ReactNode {
  const api = usePathApi();
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!menu.current?.contains(event.target as Node)) {
        setOpen(false);
        setDeleting(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!api) return null;

  async function signOut() {
    applySession(await api!.signOut().catch(() => ({ account: null, path: null })));
    setOpen(false);
  }

  async function remove() {
    setError(null);
    try {
      applySession(await api!.deleteAccount(password));
      setOpen(false);
    } catch (reason) {
      setError(message(reason));
    }
  }

  return (
    <div className={styles.account} ref={menu}>
      <button
        type="button"
        className={styles.avatarButton}
        aria-label={`Account: ${email}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className={styles.avatar} aria-hidden>
          {email.charAt(0).toUpperCase()}
        </span>
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div className={styles.menu} role="menu">
          <p className={styles.menuEmail}>{email}</p>
          {reviewer && (
            <a role="menuitem" href="/review">
              <ClipboardCheck size={15} /> Review projects
            </a>
          )}
          {reviewer && (
            <a role="menuitem" href="/report">
              <BarChart3 size={15} /> Where learners stop
            </a>
          )}
          <button type="button" role="menuitem" onClick={() => void signOut()}>
            <LogOut size={15} /> Sign out
          </button>
          {!deleting ? (
            <button type="button" role="menuitem" className={styles.danger} onClick={() => setDeleting(true)}>
              <Trash2 size={15} /> Delete account
            </button>
          ) : (
            <form
              className={styles.menuForm}
              onSubmit={(event) => {
                event.preventDefault();
                void remove();
              }}
            >
              <p>
                This deletes your account and your path for good.{" "}
                {hasPassword ? "Enter your password to confirm." : "Type your email address to confirm."}
              </p>
              <input
                type={hasPassword ? "password" : "email"}
                autoComplete={hasPassword ? "current-password" : "off"}
                aria-label={hasPassword ? "Password" : "Email address"}
                placeholder={hasPassword ? "Password" : email}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              {error && <p className={styles.error}>{error}</p>}
              <button type="submit" className={styles.dangerButton} disabled={!password}>
                Delete my account
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
