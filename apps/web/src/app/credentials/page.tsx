import { redirect } from "next/navigation";

type Props = {
  searchParams?: Promise<{ new?: string }>;
};

export default async function CredentialsLegacyPage({ searchParams }: Props) {
  const params = (await searchParams) ?? {};
  const qs = params.new === "1" ? "&new=1" : "";
  redirect(`/connections?tab=credentials${qs}`);
}
