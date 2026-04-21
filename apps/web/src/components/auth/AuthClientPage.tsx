"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api-client";
import { setStoredAuth } from "@/lib/auth";

const PASSWORD_HINT = "密码至少 6 位，只能使用字母和数字，且必须同时包含字母和数字";

interface AuthClientPageProps {
  initialMode: "login" | "register";
}

export default function AuthClientPage({ initialMode }: AuthClientPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const title = useMemo(
    () => (mode === "login" ? "登录账户" : "注册账户"),
    [mode]
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
        // Use hard navigation to ensure middleware sees the fresh auth cookie.
        window.location.assign(target);
        return;
      }
      router.replace(target);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : mode === "login"
            ? "登录失败，请检查用户名和密码"
            : "注册失败，请稍后重试"
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(238,190,120,0.22),_transparent_40%),linear-gradient(180deg,#fbf7ef_0%,#f4efe5_100%)] px-6 py-12 text-on-surface">
      <div className="mx-auto flex min-h-[calc(100vh-6rem)] max-w-6xl items-center justify-center">
        <div className="grid w-full max-w-5xl overflow-hidden rounded-[32px] border border-outline-variant/15 bg-white/80 shadow-[0_32px_120px_rgba(77,57,32,0.14)] backdrop-blur md:grid-cols-[1.05fr_0.95fr]">
          <section className="flex flex-col justify-between bg-[linear-gradient(160deg,rgba(74,107,87,0.96),rgba(42,63,53,0.96))] p-10 text-white md:p-12">
            <div>
              <p className="text-sm uppercase tracking-[0.35em] text-white/70">Med Help Agent</p>
              <h1 className="mt-6 max-w-md font-headline text-4xl font-extrabold tracking-tight md:text-5xl">
                家庭健康问诊与执行工作区
              </h1>
              <p className="mt-6 max-w-md text-sm leading-7 text-white/78 md:text-base">
                注册后可保存个人问诊、事件执行和健康档案。登录后右上角头像会显示你的个人信息入口。
              </p>
            </div>
            <div className="grid gap-4 rounded-[24px] border border-white/15 bg-white/10 p-6 text-sm text-white/85">
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-[20px]">shield_lock</span>
                <p>账号以用户名和密码登录，密码规则固定为 6 位以上字母数字组合。</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="material-symbols-outlined text-[20px]">account_circle</span>
                <p>登录后头像下拉框会显示用户名、显示名称和注册时间，并支持退出登录。</p>
              </div>
            </div>
          </section>

          <section className="p-8 md:p-12">
            <div className="mb-8 flex items-center justify-between">
              <div>
                <p className="text-sm uppercase tracking-[0.28em] text-on-surface-variant/70">Account</p>
                <h2 className="mt-3 font-headline text-3xl font-extrabold tracking-tight text-on-surface">
                  {title}
                </h2>
              </div>
              <Link href="/" className="text-sm text-primary transition hover:opacity-80">
                返回首页
              </Link>
            </div>

            <div className="mb-8 grid grid-cols-2 rounded-2xl bg-surface-container-low p-1">
              <button
                type="button"
                className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
                  mode === "login" ? "bg-white text-primary shadow-sm" : "text-on-surface-variant"
                }`}
                onClick={() => setMode("login")}
              >
                登录
              </button>
              <button
                type="button"
                className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
                  mode === "register" ? "bg-white text-primary shadow-sm" : "text-on-surface-variant"
                }`}
                onClick={() => setMode("register")}
              >
                注册
              </button>
            </div>

            <form className="space-y-5" onSubmit={handleSubmit}>
              <label className="block space-y-2">
                <span className="text-sm font-medium text-on-surface">用户名</span>
                <input
                  className="w-full rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm outline-none transition focus:border-primary/40 focus:ring-2 focus:ring-primary/15"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="请输入用户名"
                  minLength={3}
                  maxLength={64}
                  required
                />
              </label>

              <label className="block space-y-2">
                <span className="text-sm font-medium text-on-surface">密码</span>
                <input
                  type="password"
                  className="w-full rounded-2xl border border-outline-variant/20 bg-surface px-4 py-3 text-sm outline-none transition focus:border-primary/40 focus:ring-2 focus:ring-primary/15"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="请输入密码"
                  minLength={6}
                  pattern="^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{6,}$"
                  required
                />
              </label>

              <p className="rounded-2xl bg-surface-container-low px-4 py-3 text-xs leading-6 text-on-surface-variant">
                {PASSWORD_HINT}
              </p>

              {error ? (
                <p className="rounded-2xl border border-error/20 bg-error-container/60 px-4 py-3 text-sm text-error">
                  {error}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-2xl bg-primary px-4 py-3 font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "提交中..." : mode === "login" ? "立即登录" : "创建账户"}
              </button>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
