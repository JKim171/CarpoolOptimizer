/**
 * Placeholder home screen. The create-event form and the "events this browser knows about" list
 * land in the next slice; this exists so the skeleton is something you can actually load.
 */
export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold">CarpoolOptimizer</h1>
      <p className="text-sm opacity-70">
        Enter a roster, get an assignment: who drives whom, in what pickup order, out and back.
      </p>
    </main>
  );
}
