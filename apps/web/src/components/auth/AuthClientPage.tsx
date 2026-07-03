"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api-client";
import { setStoredAuth } from "@/lib/auth";
import { useLang } from "@/lib/lang-context";

interface AuthClientPageProps {
  initialMode: "login" | "register";
}

export default function AuthClientPage({ initialMode }: AuthClientPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useLang();
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const title = useMemo(
    () => (mode === "login" ? t("登录", "Sign In") : t("注册", "Sign Up")),
    [mode, t]
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const auth =
        mode === "login"
          ? await api.login(username.trim(), password)
          : await api.register(username.trim(), password);
      setStoredAuth(auth);
      const redirect = searchParams.get("redirect");
      const target =
        redirect &&
        redirect.startsWith("/") &&
        !redirect.startsWith("/auth")
          ? redirect
          : "/chat/new";
      if (typeof window !== "undefined") {
        window.location.assign(target);
        return;
      }
      router.replace(target);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : mode === "login"
            ? t("登录失败，请检查用户名和密码", "Login failed, please check your username and password")
            : t("注册失败，请稍后重试", "Registration failed, please try again later")
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center gap-2 mb-8 justify-center">
          <span className="material-symbols-outlined text-[24px] text-primary">
            local_hospital
          </span>
          <span className="font-semibold text-lg text-on-surface tracking-tight">
            {t("智愈", "SmartCare")}
          </span>
        </div>

        {/* Title */}
        <h1 className="text-xl font-semibold text-on-surface text-center mb-6">
          {title}
        </h1>

        {/* Tab switcher */}
        <div className="flex mb-6 border-b border-outline-variant/20">
          <button
            type="button"
            className={`flex-1 py-2.5 text-sm font-medium transition border-b-2 ${
              mode === "login"
                ? "border-primary text-primary"
                : "border-transparent text-on-surface-variant hover:text-on-surface"
            }`}
            onClick={() => setMode("login")}
          >
            {t("登录", "Sign In")}
          </button>
          <button
            type="button"
            className={`flex-1 py-2.5 text-sm font-medium transition border-b-2 ${
              mode === "register"
                ? "border-primary text-primary"
                : "border-transparent text-on-surface-variant hover:text-on-surface"
            }`}
            onClick={() => setMode("register")}
          >
            {t("注册", "Sign Up")}
          </button>
        </div>

        {/* Form */}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="block text-sm text-on-surface-variant mb-1.5">
              {t("用户名", "Username")}
            </label>
            <input
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none transition focus:border-primary/50 focus:ring-1 focus:ring-primary/20 placeholder:text-on-surface-variant/40"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder={t("请输入用户名", "Enter your username")}
              minLength={3}
              maxLength={64}
              required
            />
          </div>

          <div>
            <label className="block text-sm text-on-surface-variant mb-1.5">
              {t("密码", "Password")}
            </label>
            <input
              type="password"
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none transition focus:border-primary/50 focus:ring-1 focus:ring-primary/20 placeholder:text-on-surface-variant/40"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t("请输入密码", "Enter your password")}
              minLength={6}
              pattern="^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{6,}$"
              required
            />
          </div>

          <p className="text-xs text-on-surface-variant/60 leading-5">
            {t("密码至少 6 位，需同时包含字母和数字", "Password must be at least 6 characters with both letters and numbers")}
          </p>

          {error ? (
            <p className="rounded-lg border border-error/20 bg-error-container/30 px-3 py-2 text-sm text-error">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-on-primary transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? t("提交中...", "Submitting...")
              : mode === "login"
                ? t("登录", "Sign In")
                : t("注册", "Sign Up")}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-on-surface-variant/50">
          <Link href="/" className="hover:text-on-surface-variant transition-colors">
            {t("返回首页", "Back to Home")}
          </Link>
        </p>
      </div>
    </div>
  );
}
