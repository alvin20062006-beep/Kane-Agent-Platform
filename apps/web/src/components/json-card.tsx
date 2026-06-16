export function JsonCard({ data }: { data: unknown }) {
  return (
    <pre className="rounded-lg border border-zinc-200 bg-white p-4 text-xs overflow-auto">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

