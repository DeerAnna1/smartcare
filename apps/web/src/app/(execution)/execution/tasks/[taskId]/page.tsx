"use client";

import Link from "next/link";
import { useLang } from "@/lib/lang-context";

export default function TaskDetailPage() {
  const { t } = useLang();

  return (
    <div className="p-8">
      <Link href="/execution" className="text-sm text-primary hover:underline">
        ← {t("返回执行工作区", "Back to execution")}
      </Link>
      <div className="mt-6 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6">
        <h1 className="font-headline text-xl font-bold text-on-surface">
          {t("任务详情暂不可用", "Task details unavailable")}
        </h1>
        <p className="mt-2 text-sm text-on-surface-variant">
          {t("后端尚未提供单个执行任务的详情接口，因此此页不展示示例或推测数据。", "The backend does not yet expose a task-detail endpoint, so this page does not display sample or inferred data.")}
        </p>
      </div>
    </div>
  );
}
