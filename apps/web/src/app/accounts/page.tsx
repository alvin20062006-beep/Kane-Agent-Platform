import { redirect } from "next/navigation";

export default function AccountsLegacyPage() {
  redirect("/connections?tab=accounts");
}
