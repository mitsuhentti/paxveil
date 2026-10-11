"use client";
import { useState } from "react";
import { FileUp, LoaderCircle, FileText } from "lucide-react";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Modal, ErrorBanner } from "./ui";
export function Upload({ open, close, created }: { open: boolean; close: () => void; created: (project: Project) => void }) {
  const [file, setFile] = useState<File | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); if (!file) { setError("Выберите файл зависимостей."); return; }
    if (file.size > 1024 * 1024) { setError("Файл превышает 1 МБ. Загрузите только файл зависимостей."); return; }
    const data = new FormData(event.currentTarget); data.set("file", file); setBusy(true);
    try { const project = await api<Project>("/projects", { method: "POST", body: data }); created(project); setFile(null); close(); } catch (e) { setError(e instanceof Error ? e.message : "Не удалось загрузить файл"); } finally { setBusy(false); }
  }
  return <Modal open={open} onOpenChange={value => { if (!value && !busy) close(); }} title="Новый проект" description="Загрузите зависимости. PAXVEIL сохранит проект и запустит анализ реальных источников."><form onSubmit={submit} className="stack-form"><label>Название проекта<input name="name" required maxLength={100} placeholder="Например, payments-api" autoFocus/></label><label className="file-drop"><input type="file" accept=".txt,.lock" aria-label="Файл зависимостей" onChange={event => { setFile(event.target.files?.[0] || null); setError(""); }}/>{file ? <FileText size={28}/> : <FileUp size={30}/>}<strong>{file ? file.name : "Выберите файл зависимостей"}</strong><span>{file ? `${(file.size / 1024).toFixed(1)} КБ · нажмите, чтобы заменить` : "requirements.txt, poetry.lock или uv.lock · до 1 МБ"}</span></label><div className="form-grid"><label>Версия Python<select name="python_version" defaultValue="3.11">{["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"].map(x => <option key={x}>{x}</option>)}</select></label><label>Окружение<select name="platform" defaultValue="linux"><option value="linux">Linux</option><option value="windows">Windows</option><option value="darwin">macOS</option></select></label></div><p className="form-hint">Версия Python и платформа учитываются при оценке маркеров. Содержимое файла не выполняется.</p>{error && <ErrorBanner message={error}/>}<button className="button primary full" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin"/> : <FileUp size={17}/>} {busy ? "Загружаем…" : "Сохранить и проверить"}</button></form></Modal>;
}

