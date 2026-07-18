export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return <p aria-live="polite">{label}</p>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-800" role="alert">
      {message}
    </p>
  );
}
