"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import { useLang } from "@/lib/lang-context";

type EventItem = {
	event_id: string;
	status: string;
	chief_complaint: string;
	triage_level: string;
	recommended_department: string;
	created_at: string;
	archived?: boolean;
};

export default function RecordsPage() {
	const router = useRouter();
	const { lang } = useLang();
	const t = (zh: string, en: string) => lang === "zh" ? zh : en;
	const [events, setEvents] = useState<EventItem[]>([]);
	const [loading, setLoading] = useState(true);
	const [archivingId, setArchivingId] = useState<string | null>(null);

	useEffect(() => {
		let cancelled = false;

		api
			.listEvents()
			.then((data) => {
				if (cancelled) return;
				setEvents(data || []);
			})
			.catch(() => {
				if (cancelled) return;
				setEvents([]);
			})
			.finally(() => {
				if (cancelled) return;
				setLoading(false);
			});

		return () => {
			cancelled = true;
		};
	}, []);

	const archivedCount = useMemo(
		() => events.filter((event) => event.archived).length,
		[events]
	);

	const handleArchive = async (eventId: string) => {
		if (archivingId) return;
		setArchivingId(eventId);
		try {
			await api.archiveEvent(eventId);
			setEvents((prev) =>
				prev.map((event) =>
					event.event_id === eventId ? { ...event, archived: true } : event
				)
			);
		} catch {
			alert(t("归档失败，请重试", "Archive failed, please retry"));
		} finally {
			setArchivingId(null);
		}
	};

	return (
		<div className="p-8">
			<div className="mb-6">
				<div className="flex items-center gap-2 text-sm text-on-surface-variant mb-2">
					<span>{t("云端医护平台", "Cloud Medical Platform")}</span>
					<span className="material-symbols-outlined text-[14px]">chevron_right</span>
					<span className="text-on-surface font-semibold">{t("历史会话", "History")}</span>
				</div>
				<div>
					<h1 className="font-headline font-bold text-3xl text-on-surface">{t("历史会话", "Session History")}</h1>
					<p className="text-on-surface-variant text-sm mt-1">
						{t("点击会话可直接进入对应执行控制台；未归档事件可在列表中直接归档到健康档案。", "Click a session to enter the execution console; unarchived events can be archived to health records directly.")}
					</p>
				</div>
			</div>

			<div className="grid grid-cols-3 gap-4 mb-6">
				<div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-primary shadow-sm">
					<p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">{t("历史事件数", "Total Events")}</p>
					<p className="font-headline font-bold text-4xl text-primary">{events.length}</p>
					<p className="text-xs text-on-surface-variant mt-2">{t("全部健康事件", "All health events")}</p>
				</div>
				<div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-secondary shadow-sm">
					<p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">{t("已归档", "Archived")}</p>
					<p className="font-headline font-bold text-4xl text-secondary">{archivedCount}</p>
					<p className="text-xs text-on-surface-variant mt-2">{t("已进入健康档案", "Added to health records")}</p>
				</div>
				<div className="bg-surface-container-lowest rounded-2xl p-6 border-l-4 border-tertiary shadow-sm">
					<p className="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-2">{t("待归档", "Pending Archive")}</p>
					<p className="font-headline font-bold text-4xl text-tertiary">{Math.max(events.length - archivedCount, 0)}</p>
					<p className="text-xs text-on-surface-variant mt-2">{t("可手动归档", "Can be archived manually")}</p>
				</div>
			</div>

			<div className="bg-surface-container-lowest rounded-2xl border border-outline-variant/10 shadow-sm overflow-hidden">
				<div className="p-6 border-b border-outline-variant/10">
					<h2 className="font-headline font-bold text-on-surface">{t("会话列表", "Session List")}</h2>
				</div>

				{loading ? (
					<div className="p-10 text-center text-on-surface-variant">{t("加载中...", "Loading...")}</div>
				) : events.length === 0 ? (
					<div className="p-10 text-center text-on-surface-variant">{t("暂无历史会话", "No session history")}</div>
				) : (
					<div className="divide-y divide-outline-variant/10">
						{events.map((event) => {
							const createdAt = new Date(event.created_at).toLocaleString(lang === "zh" ? "zh-CN" : "en-US", { hour12: false });
							const isArchiving = archivingId === event.event_id;

							return (
								<div key={event.event_id} className="flex items-center gap-5 px-6 py-4 hover:bg-surface-container-low transition-all">
									<button
										onClick={() => router.push(`/execution?eventId=${event.event_id}`)}
										className="flex items-center gap-5 flex-1 text-left"
									>
										<div className="w-12 h-12 rounded-2xl bg-primary-fixed/60 flex items-center justify-center shrink-0">
											<span className="material-symbols-outlined text-on-surface" style={{ fontVariationSettings: "'FILL' 1" }}>
												history
											</span>
										</div>

										<div className="flex-1">
											<div className="flex items-center gap-3">
												<p className="text-xs text-on-surface-variant">{createdAt}</p>
												<p className="text-xs text-on-surface-variant">{event.recommended_department || t("未分科", "Uncategorized")}</p>
												<p className="text-xs text-on-surface-variant">{event.triage_level}</p>
											</div>
											<p className="font-semibold text-on-surface mt-0.5">{event.chief_complaint || event.triage_level || t("健康事件", "Health Event")}</p>
										</div>
									</button>

									<div className="flex items-center gap-2 shrink-0">
										<span className={`px-3 py-1 rounded-full text-xs font-semibold ${
											event.archived ? "bg-secondary-container/40 text-secondary" : "bg-error-container/40 text-error"
										}`}>
											{event.archived ? t("已归档", "Archived") : t("未归档", "Not Archived")}
										</span>
									</div>

									<div className="flex items-center gap-2 shrink-0">
										<button
											onClick={() => handleArchive(event.event_id)}
											disabled={Boolean(event.archived) || isArchiving}
											className="px-4 py-1.5 bg-primary text-on-primary rounded-xl text-xs font-semibold hover:opacity-90 transition-all disabled:opacity-50"
										>
											{event.archived ? t("已归档", "Archived") : isArchiving ? t("归档中...", "Archiving...") : t("归档", "Archive")}
										</button>
									</div>
								</div>
							);
						})}
					</div>
				)}
			</div>
		</div>
	);
}
