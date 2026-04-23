import { redirect } from "next/navigation";

export default function AgentAdaptersLegacyPage() {
  redirect("/connections?tab=adapters");
}
