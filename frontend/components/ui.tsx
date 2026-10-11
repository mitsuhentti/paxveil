"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, LoaderCircle, X, Inbox, ExternalLink } from "lucide-react";
import { safeUrl } from "@/lib/api";
export function Loading({ text = "Получаем данные…" }: { text?: string }) { return <div role="status" className="loading-state"><LoaderCircle size={24} className="spin"/><span>{text}</span></div>; }
export function Empty({ title, detail, children }: { title: string; detail: string; children?: React.ReactNode }) { return <div className="empty-state"><span className="empty-icon"><Inbox size={27}/></span><h2>{title}</h2><p>{detail}</p>{children}</div>; }
export function ErrorBanner({ message, retry }: { message: string; retry?: () => void }) { return <div role="alert" className="error-banner"><AlertTriangle size={17}/><span>{message}</span>{retry && <button onClick={retry}>Повторить</button>}</div>; }
export function Modal({ open, onOpenChange, title, description, children, wide = false }: { open: boolean; onOpenChange: (value: boolean) => void; title: string; description: string; children: React.ReactNode; wide?: boolean }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="modal-overlay"/><Dialog.Content className={`modal ${wide ? "wide" : ""}`}><div className="modal-header"><div><Dialog.Title>{title}</Dialog.Title><Dialog.Description>{description}</Dialog.Description></div><Dialog.Close className="icon-button" aria-label="Закрыть"><X size={19}/></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>;
}
export function External({ url, children }: { url: string; children?: React.ReactNode }) { const safe = safeUrl(url); return safe ? <a className="external-link" href={safe} target="_blank" rel="noopener noreferrer">{children || new URL(safe).hostname}<ExternalLink size={13}/></a> : null; }
export function valueText(value: unknown): string { return typeof value === "string" ? value : value === null || value === undefined ? "нет данных" : JSON.stringify(value, null, 2); }
export const statusLabel = (status: string) => ({ queued: "В очереди", running: "Анализируется", completed: "Завершён", partial: "Частичные данные", failed: "Ошибка", pending: "Ожидание", confirmed: "Совпадение", possible: "Возможное совпадение", no_match: "Не найдено", insufficient_data: "Недостаточно данных" }[status] || status);
