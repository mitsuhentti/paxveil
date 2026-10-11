"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, LoaderCircle } from "lucide-react";
import { Brand } from "./brand";
import { api, json } from "@/lib/api";
import type { User } from "@/lib/types";
export function AuthForm() {
  const router = useRouter(); const [register, setRegister] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { setRegister(new URLSearchParams(window.location.search).has("register")); }, []);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget);
    try { await api<User>(`/auth/${register ? "register" : "login"}`, { method: "POST", body: json({ username: data.get("username"), password: data.get("password") }) }); router.push("/app"); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось войти"); } finally { setBusy(false); }
  }
  return <main className="auth-page"><Brand/><div className="auth-panel"><p className="eyebrow">ВАШЕ РАБОЧЕЕ ПРОСТРАНСТВО</p><h1>{register ? "Создать аккаунт" : "С возвращением"}</h1><p className="muted">{register ? "Сохраните проекты, сравнивайте обновления и подключите Telegram." : "Продолжите наблюдение за зависимостями ваших проектов."}</p><form onSubmit={submit}><label>Имя пользователя<input name="username" required minLength={3} maxLength={64} pattern="[A-Za-z0-9_.-]+" autoComplete="username" placeholder="your-team"/></label><label>Пароль<input name="password" type="password" required minLength={12} maxLength={128} autoComplete={register ? "new-password" : "current-password"} placeholder={register ? "Не менее 12 символов" : "Введите пароль"}/></label>{error && <div role="alert" className="error-banner">{error}</div>}<button className="button primary full" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17}/> : <ArrowRight size={17}/>} {register ? "Создать аккаунт" : "Войти"}</button></form><p className="auth-switch">{register ? "Уже есть аккаунт?" : "Впервые здесь?"} <button onClick={() => { setRegister(!register); setError(""); }}>{register ? "Войти" : "Создать аккаунт"}</button></p></div><p className="auth-footnote mono">PAXVEIL / See the risk. Choose the fix.</p></main>;
}

