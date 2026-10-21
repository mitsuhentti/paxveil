import Link from "next/link";
import { ArrowRight, ArrowUpRight, Bell, Download, FileText, GitBranch, Send, SlidersHorizontal } from "lucide-react";
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
          <a className="button small primary" href="https://t.me/PAXVEIL_Bot">
            Открыть бота <ArrowUpRight size={16} />
          </a>
        </nav>
      </header>
      <main>
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">PAXVEIL для Python</p>
            <h1>Найдите уязвимости в зависимостях</h1>
            <p className="hero-description">
              Отправьте файл зависимостей боту. Получите отчёт об известных
              уязвимостях, сравните обновления и следите за изменениями.
            </p>
            <div className="hero-actions">
              <a className="button primary" href="https://t.me/PAXVEIL_Bot">
                Проверить в Telegram <Send size={17} />
              </a>
              <Link className="button secondary" href="/login">Открыть в браузере <ArrowRight size={16} /></Link>
            </div>
            <div className="entry-formats" aria-label="Поддерживаемые файлы">
              {formats.map((format) => <code key={format}>{format}</code>)}
            </div>
          </div>
          <div className="landing-visual">
            <div className="landing-sample">
              <div className="landing-sample-heading">
                <FileText size={18} aria-hidden="true" /><strong>requirements.txt</strong><span>Пример</span>
              </div>
              <pre><code>requests==2.31.0</code></pre>
              <div className="landing-sample-footer">
                <span>Отправьте файл боту или выберите пример в меню.</span>
                <a href="/examples/requirements.txt" download="requirements.txt"><Download size={14} aria-hidden="true" /> Скачать</a>
              </div>
            </div>
            <div className="landing-report">
              <header>
                <span className="landing-report-mark"><Mark size={26} /></span>
                <div>
                  <strong>От проверки к решению</strong>
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
                <div><strong>Варианты обновления</strong><span>Расчёт в FixLab и повторная проверка версий</span></div>
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
            <p>Для первой проверки достаточно файла зависимостей. Код проекта и сами пакеты не запускаются.</p>
          </div>
          <div className="workflow-rows">
            <article>
              <span className="step-num">01</span>
              <div>
                <h3>Загрузите зависимости</h3>
                <p>Выберите версию Python и систему проекта. Отправьте requirements.txt, poetry.lock или uv.lock размером до 1 МиБ.</p>
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
                <p>Выберите подходящий вариант в FixLab. Сервис проверит новые версии в OSV; совместимость приложения подтвердят его тесты.</p>
              </div>
            </article>
          </div>
        </section>
        <section className="landing-link">
          <div>
            <Send size={24} aria-hidden="true" />
            <h2>Следите за изменениями</h2>
            <p>Включите мониторинг для проекта. Новые уязвимости, исправления и изменения приоритетов придут в Telegram. Время и частоту уведомлений можно настроить.</p>
          </div>
          <a className="button secondary" href="https://t.me/PAXVEIL_Bot">Открыть PAXVEIL Bot <ArrowUpRight size={16} /></a>
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
