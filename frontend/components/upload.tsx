"use client";

import { useEffect, useRef, useState } from "react";
import { FileUp, LoaderCircle, FileText } from "lucide-react";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Modal, ErrorBanner } from "./ui";

const supportedFiles = ["requirements.txt", "poetry.lock", "uv.lock"];

export function Upload({ open, close, created }: {
  open: boolean;
  close: () => void;
  created: (project: Project) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setFile(null);
    setName("");
    setError("");
    setDragging(false);
    if (input.current) input.current.value = "";
  }, [open]);

  function selectFile(next: File | null) {
    setDragging(false);
    setError("");
    if (!next) return;
    if (!supportedFiles.includes(next.name)) {
      setFile(null);
      setError("Поддерживаются requirements.txt, poetry.lock и uv.lock.");
    } else if (next.size === 0 || next.size > 1024 * 1024) {
      setFile(null);
      setError(next.size === 0 ? "Файл пуст. Выберите файл с зависимостями." : "Файл больше 1 МБ. Загрузите только файл зависимостей.");
    } else {
      setFile(next);
      if (!name.trim()) setName(next.name === "requirements.txt" ? "Мой Python-проект" : next.name.replace(".lock", "-project"));
    }
  }

  function useExample() {
    setFile(new File(["# Example for a version-based vulnerability check.\nrequests==2.31.0\n"], "requirements.txt", { type: "text/plain" }));
    setName("Пример Python-проекта");
    setError("");
    if (input.current) input.current.value = "";
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!file) {
      setError("Выберите файл зависимостей.");
      return;
    }
    if (!supportedFiles.includes(file.name)) {
      setError("Поддерживаются requirements.txt, poetry.lock и uv.lock.");
      return;
    }
    if (file.size > 1024 * 1024) {
      setError("Файл больше 1 МБ. Загрузите только файл зависимостей.");
      return;
    }

    const data = new FormData(event.currentTarget);
    data.set("file", file);
    setBusy(true);
    try {
      const project = await api<Project>("/projects", { method: "POST", body: data });
      created(project);
      setFile(null);
      close();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось загрузить файл");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(value) => { if (!value && !busy) close(); }}
      title="Новый проект"
      description="Загрузите файл зависимостей. Код проекта не нужен."
    >
      <form onSubmit={submit} className="stack-form">
        <label>
          Название проекта
          <input name="name" required maxLength={100} placeholder="payments-api" value={name} onChange={event => setName(event.target.value)} autoFocus disabled={busy} />
        </label>
        <label className={`file-drop ${dragging ? "dragging" : ""}`}
          onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true); }}
          onDragLeave={event => { if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setDragging(false); }}
          onDrop={event => {
            event.preventDefault();
            if (busy) return;
            if (event.dataTransfer.files.length > 1) { setDragging(false); setError("Загрузите один файл зависимостей за раз."); return; }
            selectFile(event.dataTransfer.files[0] || null);
          }}>
          <input
            ref={input}
            type="file" accept=".txt,.lock" aria-label="Файл зависимостей"
            disabled={busy}
            onChange={(event) => selectFile(event.target.files?.[0] || null)}
          />
          {file ? <FileText size={28} /> : <FileUp size={30} />}
          <strong>{dragging ? "Отпустите файл здесь" : file ? file.name : "Выберите или перетащите файл"}</strong>
          <span>
            {file
              ? `${(file.size / 1024).toFixed(1)} КБ · нажмите, чтобы заменить`
              : "requirements.txt, poetry.lock или uv.lock · до 1 МБ"}
          </span>
        </label>
        {!file && <div className="upload-demo">
          <div><strong>Сначала посмотреть, как это работает?</strong><p className="form-hint">Пример с requests 2.31.0 пройдёт обычную проверку по источникам.</p></div>
          <button type="button" className="button secondary small" onClick={useExample}>Взять пример</button>
        </div>}
        <div className="form-grid">
          <label>
            Версия Python
            <select name="python_version" defaultValue="3.11" disabled={busy}>
              {["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"].map((version) => <option key={version}>{version}</option>)}
            </select>
          </label>
          <label>
            Платформа
            <select name="platform" defaultValue="linux" disabled={busy}>
              <option value="linux">Linux</option>
              <option value="windows">Windows</option>
              <option value="darwin">macOS</option>
            </select>
          </label>
        </div>
        <p className="form-hint">Выберите окружение проекта. Проверка начнётся после нажатия кнопки. Пакеты не устанавливаются.</p>
        {error && <ErrorBanner message={error} />}
        <button className="button primary full" disabled={busy}>
          {busy ? <LoaderCircle size={17} className="spin" /> : <FileUp size={17} />}
          {busy ? "Загрузка..." : "Создать проект и проверить"}
        </button>
      </form>
    </Modal>
  );
}
