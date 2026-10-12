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

export function Settings({ user, notify }: { user: User; notify: (message: string) => void }) {
  const [settings, setSettings] = useState<SettingsType | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [linking, setLinking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [light, setLight] = useState(true);

  useEffect(() => {
    setLight(document.documentElement.dataset.theme !== "dark");
    let active = true;
    api<SettingsType>("/settings")
      .then((data) => { if (active) setSettings(data); })
      .catch((error) => { if (active) setError(error.message); });
    return () => { active = false; };
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<SettingsType>("/settings", { method: "PUT", body: json(settings) });
      setSettings(updated);
      notify("Настройки сохранены");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось сохранить настройки");
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
    localStorage.setItem("paxveil-theme", next ? "light" : "dark");
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
              <p>Отправьте эту команду боту PAXVEIL Bot:</p>
              <button className="copy-command mono" type="button" onClick={copyCode} aria-label="Скопировать команду">
                <span>/link {code.code}</span>
                {copied ? <Check size={17} /> : <Copy size={17} />}
              </button>
              <small>Код действует до {formatDate(code.expires_at)}. После подключения обновите страницу.</small>
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
            <div><h2>Уведомления Watch</h2><p>Для всех проектов с включённым мониторингом.</p></div>
            <div className="settings-controls">
              <label>
                Минимальный приоритет <span className="mono">{settings.minimum_priority} / 100</span>
                <input
                  aria-label="Минимальный приоритет" type="range" min="0" max="100" step="5"
                  value={settings.minimum_priority}
                  onChange={(event) => setSettings({ ...settings, minimum_priority: Number(event.target.value) })}
                />
              </label>
              <div className="checkbox-list">
                {categories.map((category) => (
                  <label key={category.id}>
                    <input
                      type="checkbox" checked={settings.categories.includes(category.id)}
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
                <input type="checkbox" checked={settings.digest} onChange={(event) => setSettings({ ...settings, digest: event.target.checked })} />
                Ежедневная сводка
              </label>
            </div>
          </div>
          <div className="settings-section">
            <div><h2>Тихие часы</h2><p>В это время уведомления откладываются. Очистите оба поля, чтобы отключить.</p></div>
            <div className="settings-controls">
              <label>
                Часовой пояс
                <input
                  required name="timezone" value={settings.timezone}
                  onChange={(event) => setSettings({ ...settings, timezone: event.target.value })}
                  placeholder="Europe/Moscow" autoCapitalize="none" spellCheck={false}
                />
              </label>
              <div className="form-grid">
                <label>
                  Начало
                  <input type="time" value={settings.quiet_start || ""} onChange={(event) => setSettings({ ...settings, quiet_start: event.target.value || null })} />
                </label>
                <label>
                  Окончание
                  <input type="time" value={settings.quiet_end || ""} onChange={(event) => setSettings({ ...settings, quiet_end: event.target.value || null })} />
                </label>
              </div>
            </div>
          </div>
          <div className="settings-save">
            <button className="button primary" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}
              Сохранить настройки
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
