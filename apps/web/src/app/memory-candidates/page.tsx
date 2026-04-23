import { redirect } from "next/navigation";

// Legacy route: /memory-candidates was absorbed into /memory as the "候选待审" tab.
// Preserve old bookmarks with a permanent redirect.
export default function MemoryCandidatesLegacyPage() {
  redirect("/memory?tab=candidate");
}
