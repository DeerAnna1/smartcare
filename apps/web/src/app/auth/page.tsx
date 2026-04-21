import AuthClientPage from "@/components/auth/AuthClientPage";

export default async function AuthPage({
  searchParams,
}: {
  searchParams?: Promise<{ mode?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const initialMode = params.mode === "register" ? "register" : "login";

  return <AuthClientPage initialMode={initialMode} />;
}
