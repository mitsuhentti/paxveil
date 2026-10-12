"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, LoaderCircle } from "lucide-react";
import { Brand } from "./brand";
import { api, json } from "@/lib/api";
import type { User } from "@/lib/types";

export function AuthForm() {
  const router = useRouter();
  const [register, setRegister] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRegister(new URLSearchParams(window.location.search).has("register"));
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api<User>(`/auth/${register ? "register" : "login"}`, {
        method: "POST",
        body: json({ username: data.get("username"), password: data.get("password") }),
      });
      router.push("/app");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось войти");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <Brand />
      <div className="auth-panel">
        <h1>{register ? "Создать аккаунт" : "Вход"}</h1>
        <p className="muted">
          {register ? "Сохраняйте проекты и отчёты в своём аккаунте." : "Введите имя пользователя и пароль."}
        </p>
        <form onSubmit={submit}>
          <label>
            Имя пользователя
            <input
              name="username" required minLength={3} maxLength={64}
              pattern="[A-Za-z0-9_.-]+" autoComplete="username"
              autoCapitalize="none" spellCheck={false}
              aria-describedby={register ? "username-hint" : undefined}
            />
          </label>
          {register && <p id="username-hint" className="form-hint username-hint">От 3 символов. Латинские буквы, цифры, точка, дефис и подчёркивание.</p>}
          <label>
            Пароль
            <input
              name="password" type="password" required minLength={12} maxLength={128}
              autoComplete={register ? "new-password" : "current-password"}
              aria-describedby={register ? "password-hint" : undefined}
            />
          </label>
          {register && <p id="password-hint" className="form-hint">Не менее 12 символов.</p>}
          {error && <div role="alert" className="error-banner">{error}</div>}
          <button className="button primary full" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={17} /> : <ArrowRight size={17} />}
            {register ? "Создать аккаунт" : "Войти"}
          </button>
        </form>
        <p className="auth-switch">
          {register ? "Уже есть аккаунт?" : "Нет аккаунта?"}{" "}
          <button type="button" onClick={() => { setRegister(!register); setError(""); }}>
            {register ? "Войти" : "Создать аккаунт"}
          </button>
        </p>
      </div>
      <p className="auth-footnote">PAXVEIL · Python-зависимости</p>
    </main>
  );
}
