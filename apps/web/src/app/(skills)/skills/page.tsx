import { redirect } from "next/navigation";

/** Compatibility route. Tool management now has one canonical entry. */
export default function LegacySkillsPage() {
  redirect("/tools");
}
