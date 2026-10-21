"use client";

import { useEffect, useState } from "react";
import { Send, Copy, Check, LoaderCircle, Save, Moon, Sun } from "lucide-react";
import { api, json, formatDate } from "@/lib/api";
import type { Settings as SettingsType, User } from "@/lib/types";
import { ErrorBanner, Loading } from "./ui";

const categories = [
  { id: "new", label: "Новые уязвимости" },
  { id: "priority", label: "Рост приоритета" },
  { id: "fix", label: "Доступные исправления" },
  { id: "exploitation", label: "Подтверждённая эксплуатация" },
  { id: "status", label: "Изменения статуса" },
];

function preferences(value: SettingsType) {
  const { telegram_id: _, ...editable } = value;
  return JSON.stringify({ ...editable, categories: [...editable.categories].sort() });
}

function draftKey(userId: string) { return `paxveil-settings-draft:${userId}`; }

function restoreDraft(userId: string, current: SettingsType): SettingsType | null {
  try {
    const draft: unknown = JSON.parse(sessionStorage.getItem(draftKey(userId)) || "null");
    if (!draft || typeof draft !== "object") return null;
    const value = draft as Record<string, unknown>;
    const validTime = (time: unknown) => time === null || (typeof time === "string" && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time));
    if (typeof value.timezone !== "string" || value.timezone.length > 100 || !validTime(value.quiet_start) || !validTime(value.quiet_end)
      || typeof value.minimum_priority !== "number" || !Number.isInteger(value.minimum_priority) || value.minimum_priority < 0 || value.minimum_priority > 100
      || typeof value.digest !== "boolean" || !Array.isArray(value.categories) || !value.categories.every(category => categories.some(item => item.id === category))
      || !["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"].includes(String(value.upload_python_version))
      || !["linux", "windows", "darwin"].includes(String(value.upload_platform))) return null;
    return {
      ...current,
      timezone: value.timezone,
      quiet_start: value.quiet_start as string | null,
      quiet_end: value.quiet_end as string | null,
      minimum_priority: value.minimum_priority,
      digest: value.digest,
      categories: value.categories as string[],
      upload_python_version: value.upload_python_version as string,
      upload_platform: value.upload_platform as SettingsType["upload_platform"],
    };
  } catch { return null; }
}

export function Settings({ user, notify }: { user: User; notify: (message: string) => void }) {
  const [settings, setSettings] = useState<SettingsType | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [linking, setLinking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [light, setLight] = useState(true);
  const [saved, setSaved] = useState("");
  const [localTimezone, setLocalTimezone] = useState("");
  const [expired, setExpired] = useState(false);
  const [quietError, setQuietError] = useState("");
  const [saveError, setSaveError] = useState("");
  const dirty = settings !== null && preferences(settings) !== saved;

  useEffect(() => {
    setLight(document.documentElement.dataset.theme !== "dark");
    setLocalTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
    let active = true;
    api<SettingsType>("/settings")
      .then((data) => {
        if (!active) return;
        const draft = restoreDraft(user.id, data);
        setSettings(draft || data);
        setSaved(preferences(data));
        if (draft && preferences(draft) !== preferences(data)) notify("Восстановлены несохранённые изменения настроек");
      })
      .catch((error) => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [user.id, notify]);

  useEffect(() => {
    if (!settings || !saved) return;
    try {
      if (dirty) sessionStorage.setItem(draftKey(user.id), preferences(settings));
      else sessionStorage.removeItem(draftKey(user.id));
    } catch { /* Settings remain editable when browser storage is unavailable. */ }
  }, [settings, saved, dirty, user.id]);

  useEffect(() => {
    if (!dirty) return;
    function warn(event: BeforeUnloadEvent) { event.preventDefault(); }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    if (quietError) document.getElementById("quiet-hours-error")?.scrollIntoView({ block: "center" });
  }, [quietError]);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 3000);
    return () => clearTimeout(timer);
  }, [copied]);

  useEffect(() => {
    if (!code) return;
    let active = true;
    const timer = setInterval(async () => {
      if (new Date(code.expires_at).getTime() <= Date.now()) { setExpired(true); clearInterval(timer); return; }
      try {
        const current = await api<SettingsType>("/settings");
        if (!active || !current.telegram_id) return;
        setSettings(previous => previous ? { ...previous, telegram_id: current.telegram_id } : current);
        setCode(null);
        notify("Telegram подключён");
      } catch { /* Retry while the one-time link code remains valid. */ }
    }, 4000);
    return () => { active = false; clearInterval(timer); };
  }, [code, notify]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setQuietError("");
    setSaveError("");
    if (Boolean(settings.quiet_start) !== Boolean(settings.quiet_end)) {
      setQuietError("Укажите начало и окончание тихих часов или очистите оба поля.");
      document.getElementById(settings.quiet_start ? "quiet-end" : "quiet-start")?.focus();
      return;
    }
    if (settings.quiet_start && settings.quiet_start === settings.quiet_end) {
      setQuietError("Начало и окончание тихих часов должны отличаться.");
      document.getElementById("quiet-end")?.focus();
      return;
    }
    setBusy(true);
    setError("");
    try {
      const { telegram_id: _, ...editable } = settings;
      const updated = await api<SettingsType>("/settings", { method: "PUT", body: json(editable) });
      setSettings(updated);
      setSaved(preferences(updated));
      notify("Настройки сохранены");
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Не удалось сохранить настройки");
    } finally {
      setBusy(false);
    }
  }

  async function link() {
    setLinking(true);
    setError("");
    try {
      setCode(await api<{ code: string; expires_at: string }>("/auth/telegram/link", { method: "POST" }));
      setCopied(false);
      setExpired(false);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось получить код");
    } finally {
      setLinking(false);
    }
  }

  async function copyCode() {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(`/link ${code.code}`);
      setCopied(true);
    } catch {
      notify("Не удалось скопировать. Выделите команду вручную.");
    }
  }

  function theme() {
    const next = !light;
    setLight(next);
    document.documentElement.dataset.theme = next ? "light" : "dark";
    try { localStorage.setItem("paxveil-theme", next ? "light" : "dark"); } catch { /* The selected theme still applies to this page. */ }
  }

  return (
    <section className="settings-page">
      <div className="page-heading">
        <div><h1>Настройки</h1><p>Аккаунт, Telegram и уведомления.</p></div>
      </div>
      {error && <ErrorBanner message={error} />}
      <div className="settings-section">
        <div><h2>Аккаунт</h2><p>Имя пользователя</p></div>
        <div className="settings-account"><strong>{user.username}</strong></div>
      </div>
      <div className="settings-section">
        <div>
          <h2><Send size={19} /> Telegram</h2>
          <p>Подключите бота для работы с проектами и получения уведомлений.</p>
        </div>
        <div className="settings-controls">
          {settings?.telegram_id ? (
            <div className="connected-label"><Check size={17} /> Подключён · {settings.telegram_id}</div>
          ) : (
            <button className="button secondary" type="button" onClick={link} disabled={linking}>
              {linking && <LoaderCircle className="spin" size={15} />} Получить код
            </button>
          )}
          {code && (
            <div className="link-code">
              <p>Скопируйте команду и отправьте её <a className="text-button" href="https://t.me/PAXVEIL_Bot" target="_blank" rel="noopener noreferrer">@PAXVEIL_Bot</a>:</p>
              <button className="copy-command mono" type="button" onClick={copyCode} aria-label={copied ? "Команда скопирована" : "Скопировать команду"} disabled={expired}>
                <span>/link {code.code}</span>
                {copied ? <Check size={17} /> : <Copy size={17} />}
              </button>
              <small role="status">{expired ? "Срок кода истёк. Получите новый код." : `Код действует до ${formatDate(code.expires_at)}. Подключение появится здесь автоматически.`}</small>
            </div>
          )}
        </div>
      </div>
      <div className="settings-section">
        <div><h2>Тема</h2><p>Сохраняется в этом браузере.</p></div>
        <button className="button secondary" type="button" onClick={theme}>
          {light ? <Moon size={17} /> : <Sun size={17} />}
          {light ? "Тёмная тема" : "Светлая тема"}
        </button>
      </div>
      {!settings && !error && <Loading />}
      {settings && (
        <form className="settings-form" onSubmit={save}>
          <div className="settings-section">
            <div><h2>Файлы из Telegram</h2><p>Окружение для новых проектов, загруженных в боте.</p></div>
            <div className="settings-controls form-grid">
              <label>Python
                <select disabled={busy} value={settings.upload_python_version || "3.11"} onChange={(event) => setSettings({ ...settings, upload_python_version: event.target.value })}>
                  {["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"].map((version) => <option key={version} value={version}>{version}</option>)}
                </select>
              </label>
              <label>Система
                <select disabled={busy} value={settings.upload_platform || "linux"} onChange={(event) => setSettings({ ...settings, upload_platform: event.target.value as SettingsType["upload_platform"] })}>
                  <option value="linux">Linux</option><option value="windows">Windows</option><option value="darwin">macOS</option>
                </select>
              </label>
            </div>
          </div>
          <div className="settings-section">
            <div><h2>Уведомления</h2><p>Для всех проектов с включённым мониторингом.</p></div>
            <div className="settings-controls">
              <label>
                Минимальный приоритет <span className="mono">{settings.minimum_priority} / 100</span>
                <input disabled={busy}
                  aria-label="Минимальный приоритет" type="range" min="0" max="100" step="5"
                  value={settings.minimum_priority}
                  onChange={(event) => setSettings({ ...settings, minimum_priority: Number(event.target.value) })}
                />
              </label>
              <div className="checkbox-list">
                {categories.map((category) => (
                  <label key={category.id}>
                    <input
                      type="checkbox" disabled={busy} checked={settings.categories.includes(category.id)}
                      onChange={(event) => setSettings({
                        ...settings,
                        categories: event.target.checked
                          ? [...settings.categories, category.id]
                          : settings.categories.filter((id) => id !== category.id),
                      })}
                    />
                    {category.label}
                  </label>
                ))}
              </div>
              <label className="check-label">
                <input type="checkbox" disabled={busy} checked={settings.digest} onChange={(event) => setSettings({ ...settings, digest: event.target.checked })} />
                Ежедневная сводка
              </label>
              {settings.categories.length === 0 && <p className="form-hint">События не выбраны. Уведомления отправляться не будут.</p>}
            </div>
          </div>
          <div className="settings-section">
            <div><h2>Тихие часы</h2><p>В это время уведомления откладываются. Очистите оба поля, чтобы отключить.</p></div>
            <div className="settings-controls">
              <label>
                Часовой пояс
                <input
                  required name="timezone" value={settings.timezone} list="timezones" disabled={busy}
                  onChange={(event) => setSettings({ ...settings, timezone: event.target.value })}
                  placeholder="Europe/Moscow" autoCapitalize="none" spellCheck={false}
                />
              </label>
              <datalist id="timezones">{Array.from(new Set([localTimezone, "Europe/Moscow", "Europe/London", "Europe/Berlin", "Asia/Almaty", "Asia/Tbilisi", "Asia/Yekaterinburg", "Asia/Novosibirsk", "America/New_York", "UTC"]))
                .filter(Boolean).map(zone => <option key={zone} value={zone} />)}</datalist>
              {localTimezone && settings.timezone !== localTimezone && <button className="text-button" type="button" disabled={busy} onClick={() => setSettings({ ...settings, timezone: localTimezone })}>Использовать мой пояс: {localTimezone}</button>}
              <div className="form-grid">
                <label>
                  Начало
                  <input id="quiet-start" type="time" disabled={busy} value={settings.quiet_start || ""} aria-invalid={!!quietError} aria-describedby={quietError ? "quiet-hours-error" : undefined} onChange={(event) => { setQuietError(""); setSettings({ ...settings, quiet_start: event.target.value || null }); }} />
                </label>
                <label>
                  Окончание
                  <input id="quiet-end" type="time" disabled={busy} value={settings.quiet_end || ""} aria-invalid={!!quietError} aria-describedby={quietError ? "quiet-hours-error" : undefined} onChange={(event) => { setQuietError(""); setSettings({ ...settings, quiet_end: event.target.value || null }); }} />
                </label>
              </div>
              {quietError && <div id="quiet-hours-error"><ErrorBanner message={quietError} /></div>}
              {(settings.quiet_start || settings.quiet_end) && <button className="text-button" type="button" disabled={busy} onClick={() => { setQuietError(""); setSettings({ ...settings, quiet_start: null, quiet_end: null }); }}>Отключить тихие часы</button>}
            </div>
          </div>
          <div className="settings-save">
            {saveError && <ErrorBanner message={saveError} />}
            <span className="settings-dirty" role="status">{busy ? "Сохранение..." : dirty ? "Есть несохранённые изменения" : "Все изменения сохранены"}</span>
            <button className="button primary" disabled={busy || !dirty}>
              {busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}
              Сохранить настройки
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
