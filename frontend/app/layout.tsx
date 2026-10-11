import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: { default: "PAXVEIL — See the risk. Choose the fix.", template: "%s · PAXVEIL" }, description: "Реальный анализ уязвимостей Python-зависимостей, варианты обновлений и мониторинг в Telegram.", icons: { icon: "/icon.svg" } };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="ru" data-scroll-behavior="smooth"><body>{children}</body></html>; }
