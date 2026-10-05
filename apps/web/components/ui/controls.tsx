/**
 * Form and layout primitives.
 *
 * These exist because the roster table and the results list will copy whatever pattern is in front
 * of them. One definition of "what an input looks like" is cheap now and expensive once three
 * screens have their own.
 *
 * Deliberately plain: no variant systems, no polymorphic `as` props, no class-merging helper. The
 * app has one visual language and a handful of controls, and the abstraction that fits that is a
 * function that returns the right element.
 *
 * Three conventions the screens rely on, written here because nowhere else can enforce them:
 *
 *  - **A rule separates; a box contains.** Almost nothing here is a box. The screen was a stack of
 *    bordered cards on a tinted plane, which is how every generated dashboard looks and which says
 *    nothing: a border around a thing that nobody was going to confuse with its neighbour is
 *    decoration. Sections are divided by a hairline and by space. The surviving boxes are the ones
 *    that genuinely contain something you can act on -- an input, the warn block.
 *  - **Type scale.** Page title `font-display text-3xl/4xl`, section heading `font-display
 *    text-xl`, sub-heading `font-display text-base`, body `text-[15px]`, dense rows and meta
 *    `text-sm`/`text-xs`. There is one family, so `font-display` is a *treatment* rather than a
 *    face -- it sets weight and tracking, defined once in `globals.css`. Never add `font-bold`
 *    beside it; that is the thing it exists to decide.
 *  - **Labels are set in sentence case, not `uppercase tracking-wide`.** Tiny letterspaced capitals
 *    on every label is the other tell of a generated interface, and it costs legibility for
 *    nothing. A label is small and quiet; that is enough to make it a label.
 */

import type { ReactNode, SelectHTMLAttributes } from "react";

/** 2px, not `rounded-md`. Print has corners; a 6px radius on every element is a house style. */
const CONTROL =
  "w-full rounded-[2px] border border-line bg-surface-raised px-3 py-2 text-[15px] text-ink " +
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
    "rounded-[2px] text-sm font-medium transition-colors disabled:opacity-50 " +
    (variant === "ghost" ? "px-2 py-1" : "px-4 py-2");
  const look = {
    primary: "bg-accent text-accent-ink hover:bg-accent-hover",
    quiet: "border border-line-strong text-ink hover:bg-surface-sunken",
    ghost: "text-ink-muted hover:text-ink hover:underline",
  }[variant];
  return <button {...props} className={`${base} ${look}`} />;
}

/**
 * An error the operator has to act on.
 *
 * `role="alert"` so it is announced rather than silently appearing below the fold -- these messages
 * are the difference between a stuck form and a fixed one. Marked with a heavy rule down the side
 * rather than a filled box: it has to be found while scanning, and on a paper-coloured page a bar
 * in the margin does that at least as well as a tinted rectangle.
 */
export function Problem({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="border-l-2 border-danger-ink bg-danger-surface py-2 pl-3 pr-3 text-[15px] text-danger-ink"
    >
      {children}
    </p>
  );
}

/** A warning the operator should see but need not act on before continuing. */
export function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="border-l-2 border-warn-line bg-warn-surface py-2 pl-3 pr-3 text-[15px] text-warn-ink">
      {children}
    </p>
  );
}

/**
 * A short value picked out of its surroundings: a role in a table column, an event's handle.
 *
 * `tone` says what kind of thing it is, not what colour to use. `accent` is for the one value in a
 * column that changes what the row *means* -- a driver among passengers -- and is deliberately the
 * only tone that tints, so that a table with one badge per row still reads as a table. `plain` is
 * the same chip without the claim to attention.
 */
export function Badge({
  tone = "plain",
  mono = false,
  children,
}: {
  tone?: "plain" | "accent";
  /** For machine-readable handles, where a reader compares characters rather than reading words. */
  mono?: boolean;
  children: ReactNode;
}) {
  const look =
    tone === "accent" ? "bg-accent-soft text-accent-soft-ink" : "bg-surface-sunken text-ink-muted";
  return (
    <span
      className={`inline-flex items-center rounded-[2px] px-1.5 py-0.5 text-xs ${
        mono ? "font-mono" : "font-medium"
      } ${look}`}
    >
      {children}
    </span>
  );
}

/**
 * A hairline divider.
 *
 * The workhorse of this layout: what used to be a border around every block is now a line between
 * blocks, which is the same information and a great deal less furniture.
 */
export function Rule({ className = "" }: { className?: string }) {
  return <hr className={`border-0 border-t border-line ${className}`} />;
}

/**
 * A bordered block, for the few things that really are containers.
 *
 * Kept for forms -- a set of fields genuinely is one object, and the border is what says where it
 * starts and stops. Everything that was a `Panel` merely to look tidy is a `Section` with a rule.
 */
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
    <div className={`rounded-[2px] border border-line bg-surface-raised p-5 ${className}`}>
      {title && <h3 className="mb-4 font-display text-base text-ink">{title}</h3>}
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
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
      <h2 className="font-display text-xl text-ink">{title}</h2>
      {(meta || actions) && (
        <div className="flex items-center gap-3">
          {meta && <span className="text-xs text-ink-muted">{meta}</span>}
          {actions}
        </div>
      )}
    </div>
  );
}

/**
 * A titled block of the page, opened by a rule.
 *
 * The rule above the heading is what replaced the border around everything: it says "a new thing
 * starts here" using one line instead of four, and it is how a printed page has always done it.
 */
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
    <section className="flex flex-col gap-5">
      <div className="flex flex-col gap-3">
        <Rule />
        <SectionHeading title={title} meta={meta} actions={actions} />
      </div>
      {children}
    </section>
  );
}

/**
 * Page frame. One place decides max width and gutters, so screens cannot disagree about them.
 *
 * `max-w-5xl`: the event screen is a five-column roster table and a list of routes, and narrower
 * than this it ran as a ribbon with two thirds of a laptop screen empty beside it. Running prose is
 * capped well inside it per-screen rather than here, since the table wants the full measure and a
 * paragraph does not.
 */
export function Page({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 p-6 sm:p-8">
      {children}
    </main>
  );
}

/**
 * Escapes the page's measure to the full width of the window.
 *
 * For the map, which is the one element here that is better the bigger it is -- it is the thing
 * being verified, and at the width of a column of text it was a thumbnail. Everything else on the
 * page is read, and reading wants a measure.
 *
 * The `left-1/2 w-screen -translate-x-1/2` trick measures `100vw`, which includes the scrollbar
 * gutter; `overflow-x-clip` on the body in `layout.tsx` is what keeps that from showing up as a few
 * pixels of horizontal scroll, and it has to be `clip` rather than `hidden` so that nothing inside
 * loses `position: sticky`.
 */
export function Bleed({ children }: { children: ReactNode }) {
  return <div className="relative left-1/2 w-screen -translate-x-1/2">{children}</div>;
}

/** A label/value pair, for the read-only summaries on the event page. */
export function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="mt-1 text-[15px] text-ink">{children}</dd>
    </div>
  );
}
