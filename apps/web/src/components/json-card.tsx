export function JsonCard({ data }: { data: unknown }) {
  return (
    <pre className="kane-paper overflow-auto p-4 text-xs text-[var(--foreground)]">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

