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
 *
 * Two conventions the screens rely on, written here because nowhere else can enforce them:
 *
 *  - **Type scale.** Page title `text-2xl/3xl`, section heading `text-base`, sub-heading and body
 *    `text-sm`, meta `text-xs`. Headings were all `text-sm font-medium` at one point, which made a
 *    section indistinguishable from the thing inside it -- "Add people" read exactly like its own
 *    child "Paste a roster". `SectionHeading` and `Panel`'s `title` exist so that cannot recur.
 *  - **Radius says what a thing is.** Containers are `rounded-lg`, controls `rounded-md`. When
 *    both were `rounded-md` on the same surface, a route card and a text input were the same
 *    object at a glance.
 */

import type { ReactNode, SelectHTMLAttributes } from "react";

const CONTROL =
  "w-full rounded-md border border-line bg-surface-raised px-3 py-2 text-sm text-ink " +
  "transition-colors placeholder:text-ink-muted hover:border-line-strong disabled:opacity-50";

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
      <div className="mt-1.5">{children}</div>
      {hint && <span className="mt-1.5 block text-xs text-ink-muted">{hint}</span>}
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

/**
 * `ghost` is for actions that repeat once per row.
 *
 * A fifty-row roster carries a hundred of them, and as bordered buttons they out-shout the names
 * and addresses they act on -- the table became a grid of rectangles with the data in between.
 * Ghost keeps the hit area and drops the box.
 */
export function Button({
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "quiet" | "ghost";
}) {
  const base =
    "rounded-md text-sm font-medium transition-colors disabled:opacity-50 " +
    (variant === "ghost" ? "px-2 py-1" : "px-4 py-2");
  const look = {
    primary: "bg-accent text-accent-ink hover:bg-accent-hover",
    quiet: "border border-line text-ink hover:border-line-strong hover:bg-surface-sunken",
    ghost: "text-ink-muted hover:bg-surface-sunken hover:text-ink",
  }[variant];
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

/** A warning the operator should see but need not act on before continuing. */
export function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-warn-line bg-warn-surface px-3 py-2 text-sm text-warn-ink">
      {children}
    </p>
  );
}

export function Panel({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-lg border border-line bg-surface-raised p-5 ${className}`}>
      {title && <h3 className="mb-4 text-sm font-semibold text-ink">{title}</h3>}
      {children}
    </div>
  );
}

/**
 * A section heading, with room for the status and controls that belong beside it.
 *
 * `meta` is the quiet right-hand note ("Refreshing…", a job status); `actions` is the button. Both
 * were previously open-coded as a flex row per screen, and they had drifted apart on alignment.
 */
export function SectionHeading({
  title,
  meta,
  actions,
}: {
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <h2 className="text-base font-semibold tracking-tight text-ink">{title}</h2>
      {(meta || actions) && (
        <div className="flex items-center gap-3">
          {meta && <span className="text-xs text-ink-muted">{meta}</span>}
          {actions}
        </div>
      )}
    </div>
  );
}

/** A titled block of the page. One definition of the gap between a heading and what it heads. */
export function Section({
  title,
  meta,
  actions,
  children,
}: {
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4">
      <SectionHeading title={title} meta={meta} actions={actions} />
      {children}
    </section>
  );
}

/**
 * Page frame. One place decides max width and gutters, so screens cannot disagree about them.
 *
 * `max-w-5xl`, not `3xl`: the event screen is a five-column roster table, a map and a column of
 * route cards, and at 3xl it ran as a narrow ribbon with two thirds of a laptop screen empty
 * beside it. This is still a measure that reads -- the prose on the create screen is the widest
 * running text and sits well inside it.
 */
export function Page({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 p-6 sm:p-8">
      {children}
    </main>
  );
}

/** A label/value pair, for the read-only summaries on the event page. */
export function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{children}</dd>
    </div>
  );
}
