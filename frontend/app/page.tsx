import Link from "next/link";
import { ArrowRight, ArrowUpRight, Bell, FileText, GitBranch, Send, SlidersHorizontal } from "lucide-react";
import { Brand, Mark } from "@/components/brand";

const formats = ["requirements.txt", "poetry.lock", "uv.lock"];

export default function Landing() {
  return (
    <div className="landing">
      <header className="landing-nav">
        <Brand />
        <nav aria-label="Главная навигация">
          <a href="#workflow">Как это работает</a>
          <Link href="/login">Войти</Link>
          <Link className="button small primary" href="/login?register=1">
            Создать аккаунт <ArrowUpRight size={16} />
          </Link>
        </nav>
      </header>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">Python / зависимости</p>
            <h1>Проверка зависимостей Python</h1>
            <p className="hero-description">
              Загрузите файл проекта, найдите известные уязвимости и сравните
              варианты обновления пакетов.
            </p>
            <div className="hero-actions">
              <Link className="button primary" href="/login?register=1">
                Проверить проект <ArrowRight size={18} />
              </Link>
              <a className="button secondary" href="#workflow">Как это работает</a>
            </div>
            <div className="entry-formats" aria-label="Поддерживаемые файлы">
              {formats.map((format) => <code key={format}>{format}</code>)}
            </div>
          </div>
          <div className="landing-visual">
            <div className="landing-file">
              <FileText size={20} aria-hidden="true" />
              <div>
                <strong>Файл зависимостей</strong>
                <span>Точные версии пакетов и параметры окружения</span>
              </div>
            </div>
            <div className="landing-report">
              <header>
                <span className="landing-report-mark"><Mark size={26} /></span>
                <div>
                  <strong>Что будет в отчёте</strong>
                  <span>Сохраняется в вашем проекте</span>
                </div>
              </header>
              <div className="landing-report-row">
                <GitBranch size={18} aria-hidden="true" />
                <div><strong>Состав проекта</strong><span>Пакеты, версии и связи</span></div>
              </div>
              <div className="landing-report-row">
                <Bell size={18} aria-hidden="true" />
                <div><strong>Уязвимости</strong><span>Приоритет, описание и ссылки на источники</span></div>
              </div>
              <div className="landing-report-row">
                <SlidersHorizontal size={18} aria-hidden="true" />
                <div><strong>Варианты обновления</strong><span>Новые версии и проверка совместимости зависимостей</span></div>
              </div>
            </div>
          </div>
        </section>
        <div className="source-strip">
          <span>Источники данных</span>
          <strong>OSV</strong><strong>PyPI</strong><strong>deps.dev</strong>
          <strong>FIRST EPSS</strong><strong>CISA KEV</strong>
        </div>
        <section id="workflow" className="workflow">
          <div className="section-intro">
            <h2>Как проверить проект</h2>
            <p>Исходный код загружать не нужно. Для анализа достаточно файла зависимостей.</p>
          </div>
          <div className="workflow-rows">
            <article>
              <span className="step-num">01</span>
              <div>
                <h3>Загрузите зависимости</h3>
                <p>Укажите версию Python и платформу проекта. PAXVEIL разберёт пакеты и маркеры окружения.</p>
              </div>
            </article>
            <article>
              <span className="step-num">02</span>
              <div>
                <h3>Посмотрите отчёт</h3>
                <p>Проверьте найденные уязвимости, приоритеты и дату получения данных. Предыдущие проверки доступны в истории.</p>
              </div>
            </article>
            <article>
              <span className="step-num">03</span>
              <div>
                <h3>Сравните обновления</h3>
                <p>FixLab подберёт версии и проверит зависимости. Перед обновлением проекта запустите его тесты.</p>
              </div>
            </article>
          </div>
        </section>
        <section className="landing-link">
          <div>
            <Send size={24} aria-hidden="true" />
            <h2>Уведомления в Telegram</h2>
            <p>Подключите бота и включите Watch для нужных проектов. Уведомления придут при появлении уязвимостей и изменении приоритетов.</p>
          </div>
          <Link className="button secondary" href="/login">Открыть проекты <ArrowUpRight size={16} /></Link>
        </section>
      </main>
      <footer className="landing-footer">
        <span><Mark size={20} /> PAXVEIL</span>
        <span>Анализ Python-зависимостей</span>
        <Link href="/login">Войти <ArrowUpRight size={15} /></Link>
      </footer>
    </div>
  );
}
