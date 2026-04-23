import { HelpDocClient } from "./help-doc-client";

export default async function HelpDocPage({
  params,
}: {
  params: Promise<{ doc: string }>;
}) {
  const { doc } = await params;
  return <HelpDocClient doc={doc} />;
}
