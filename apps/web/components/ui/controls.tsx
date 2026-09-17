/**
 * Form and layout primitives.
 *
 * These exist because the next two slices add a fifty-row roster table and a results sidebar, and
 * both will copy whatever pattern is in front of them. One definition of "what an input looks like"
 * is cheap now and expensive once three screens have their own.
 *
 * Deliberately plain: no variant systems, no polymorphic `as` props, no class-merging helper. The
 * app has one visual language and a handful of controls, and the abstraction that fits that is a
 * function that returns the right element.
 */

import type { ReactNode, SelectHTMLAttributes } from "react";

const CONTROL =
  "w-full rounded-md border border-line bg-surface-raised px-3 py-2 text-sm text-ink " +
  "placeholder:text-ink-muted hover:border-line-strong disabled:opacity-50";

/** A labelled control, with room for the "why" text a coordinator needs at the point of entry. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-ink">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-xs text-ink-muted">{hint}</span>}
    </label>
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={CONTROL} />;
}

export function Select({
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select {...props} className={CONTROL}>
      {children}
    </select>
  );
}

export function Button({
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "quiet" }) {
  const base = "rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50";
  const look =
    variant === "primary"
      ? "bg-accent text-accent-ink hover:bg-accent-hover"
      : "border border-line text-ink hover:border-line-strong";
  return <button {...props} className={`${base} ${look}`} />;
}

/**
 * An error the operator has to act on.
 *
 * `role="alert"` so it is announced rather than silently appearing below the fold -- these messages
 * are the difference between a stuck form and a fixed one.
 */
export function Problem({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-md bg-danger-surface px-3 py-2 text-sm text-danger-ink">
      {children}
    </p>
  );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-md border border-line bg-surface-raised p-4 ${className}`}>
      {children}
    </div>
  );
}

/** Page frame. One place decides max width and gutters, so screens cannot disagree about them. */
export function Page({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-6 sm:p-8">
      {children}
    </main>
  );
}

/** A label/value pair, for the read-only summaries on the event page. */
export function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  );
}
