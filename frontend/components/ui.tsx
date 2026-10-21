"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, LoaderCircle, X, Inbox, ExternalLink } from "lucide-react";
import { safeUrl } from "@/lib/api";

export function Loading({ text = "Загрузка данных" }: { text?: string }) {
  return (
    <div role="status" aria-live="polite" className="loading-state">
      <LoaderCircle size={22} className="spin" aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

export function Empty({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true"><Inbox size={24} /></span>
      <h2>{title}</h2>
      <p>{detail}</p>
      {children}
    </div>
  );
}

export function ErrorBanner({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div role="alert" className="error-banner">
      <AlertTriangle size={18} aria-hidden="true" />
      <span>{displayText(message)}</span>
      {retry && <button type="button" onClick={retry}>Повторить</button>}
    </div>
  );
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  title: string;
  description: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content className={`modal ${wide ? "wide" : ""}`}>
          <div className="modal-header">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Description>{description}</Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Закрыть">
              <X size={19} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function External({ url, children }: { url: string; children?: React.ReactNode }) {
  const safe = safeUrl(url);
  if (!safe) return null;

  return (
    <a className="external-link" href={safe} target="_blank" rel="noopener noreferrer">
      {children || new URL(safe).hostname}
      <ExternalLink size={13} />
    </a>
  );
}

export function valueText(value: unknown): string {
  if (typeof value === "string") return displayText(value);
  return value === null || value === undefined ? "Нет данных" : JSON.stringify(value, null, 2);
}

const messages: Record<string, string> = {
  "A requirements file does not establish whether all transitive dependencies are pinned. Submitted entries are treated as roots for simulation.":
    "Проверены пакеты из requirements.txt. Полнота транзитивных зависимостей неизвестна. Для расчёта обновлений пакеты из файла считаются прямыми.",
  "uv.lock has no project root; direct versus transitive status is unknown.":
    "В uv.lock нет корня проекта. Тип зависимостей неизвестен.",
  "poetry.lock alone has no root requirements; direct versus transitive status and original version bounds are unknown.":
    "В poetry.lock не указаны прямые зависимости и исходные ограничения версий. Нужен pyproject.toml.",
  "No advisory summary supplied.": "Источник не предоставил описание.",
  "CISA KEV listing adds 25: exploitation in the wild is documented.":
    "Запись в CISA KEV добавляет 25 баллов. Каталог подтверждает случаи эксплуатации.",
  "This is a known-vulnerability version analysis. Application reachability and exploitability are not tested.":
    "Проверены версии пакетов. Использование уязвимого кода в приложении не проверялось.",
  "requirements.txt describes submitted roots only; unlisted transitive dependencies are not assumed to be installed.":
    "Проверены пакеты из requirements.txt. Транзитивные зависимости, которых нет в файле, не проверялись.",
  "deps.dev metadata cross-check was bounded to the first 10 recorded releases; OSV covers all eligible exact pins.":
    "В deps.dev сверены первые 10 версий. В OSV проверены все поддерживаемые пакеты с точными версиями.",
  "Resolution uses official PyPI binary metadata; package code and application tests are never executed.":
    "Расчёт использует метаданные PyPI. Код пакетов и тесты приложения не запускаются.",
  "A resolved environment is a proposal, not a guarantee of behavioral compatibility.":
    "После обновления нужно проверить совместимость и запустить тесты приложения.",
  "Target architecture is x86_64; machine, optional extras and original root bounds may be incomplete.":
    "Расчёт выполнен для x86_64. Данные об extras и исходных ограничениях версий могут быть неполными.",
  "requirements.txt pins are treated as simulation roots. poetry.lock without a project manifest has unknown roots and cannot be resolved faithfully.":
    "Пакеты из requirements.txt считаются прямыми зависимостями. Для poetry.lock без pyproject.toml прямые зависимости неизвестны.",
  "Maximum Coverage may relax non-pin version bounds; review and test the proposal before applying.":
    "Полное обновление может выйти за исходные ограничения версий. Проверьте изменения перед применением.",
  "Smallest newer stable release in the same major/minor family, subject to recorded non-pin bounds.":
    "Ближайшая стабильная версия в пределах текущей minor-ветки и заданных ограничений.",
  "Newest stable release in the same major family, subject to recorded non-pin bounds.":
    "Последняя стабильная версия в пределах текущей major-ветки и заданных ограничений.",
  "Newest stable release across major families; original non-pin bounds are relaxed explicitly.":
    "Последняя стабильная версия, включая новую major-ветку. Исходные ограничения могут быть пересмотрены.",
  "Exact, supported dependencies and known project roots are required for a faithful resolution. Upload a complete pinned requirements file or uv.lock with a project root.":
    "Для расчёта нужны точные версии и известные прямые зависимости. Загрузите полный requirements.txt или uv.lock с корнем проекта.",
  "The source report contains no known findings. No remediation target was inferred.":
    "В исходном отчёте нет известных уязвимостей. Обновления для исправления не рассчитаны.",
  "No verified update proposal could be formed within this strategy.":
    "В пределах этой стратегии не удалось подобрать проверенное обновление.",
  "No valid binary-only resolution was produced. Vulnerabilities after this proposal were not evaluated.":
    "Совместимый набор wheel-пакетов не найден. Уязвимости после обновления не проверены.",
  "A version match does not demonstrate application reachability or exploitability.":
    "Совпадение версии не подтверждает, что уязвимый код используется в приложении.",
  "A single lock file may omit root paths, extras or platform selection.":
    "Lock-файл может не содержать прямые зависимости, extras и выбор платформы.",
  "OSV has no retrievable advisory for this CVE or its aliases in your existing reports. Absence is insufficient to establish that projects are unaffected.":
    "В OSV не найдена доступная запись для этого CVE. По этим данным нельзя исключить риск для проектов.",
  "EPSS unavailable; no exploitation probability was inferred.":
    "EPSS недоступен. Вероятность эксплуатации неизвестна.",
  "CISA KEV source unavailable; exploitation evidence is unknown.":
    "CISA KEV недоступен. Данные о подтверждённой эксплуатации неизвестны.",
  "Submitted root dependency adds 5 for remediation visibility.":
    "Прямая зависимость добавляет 5 баллов к приоритету.",
  "Priority is a PAXVEIL triage policy (0–100), not proof of application reachability or exploitability.":
    "Приоритет от 0 до 100 помогает выбрать порядок исправления. Он не подтверждает эксплуатацию в приложении.",
};

export function displayText(message: string): string {
  if (messages[message]) return messages[message];

  const translations: Array<[RegExp, string]> = [
    [/^Line (\d+): installer option, include, editable or index directive was ignored; no files or URLs were followed\.$/,
      "Строка $1: настройка установки пропущена. Внешние файлы и ссылки не загружались."],
    [/^(.*): direct URLs, VCS and local sources are unsupported and were not fetched\.$/,
      "$1: зависимости из ссылок, VCS и локальных источников не поддерживаются и не загружались."],
    [/^(.*): an exact version is missing; vulnerability status is unknown\.$/,
      "$1: точная версия не указана. Проверить уязвимости нельзя."],
    [/^(.*): a non-PyPI source cannot be mapped safely to PyPI advisories\.$/,
      "$1: пакет из другого источника нельзя достоверно сопоставить с записями PyPI."],
    [/^(.*): Python constraint could not be interpreted\.$/, "$1: ограничение версии Python не удалось разобрать."],
    [/^(.*): lock includes optional extras; selection is not fully known from this file\.$/,
      "$1: файл содержит extras. Выбор дополнительных зависимостей неизвестен."],
    [/^(.*): unsupported dependency edge\.$/, "$1: связь между зависимостями не поддерживается."],
    [/^(.*): lock edge could not be resolved uniquely\.$/, "$1: связь в lock-файле не удалось определить однозначно."],
    [/^(.*): multiple versions may apply in this environment; scan covers each recorded version\.$/,
      "$1: в этом окружении возможны несколько версий. Проверена каждая указанная версия."],
    [/^(.*) declares Requires-Python (.*); the submitted environment may be incompatible\.$/,
      "$1 требует Python $2. Указанное окружение может быть несовместимо."],
    [/^(.*): invalid Requires-Python metadata from PyPI\.$/, "$1: некорректные метаданные Requires-Python в PyPI."],
    [/^(.*): invalid Requires-Dist metadata was ignored\.$/, "$1: некорректные метаданные Requires-Dist пропущены."],
    [/^(.*): direct-URL metadata dependency was not followed\.$/, "$1: зависимость по прямой ссылке не загружалась."],
    [/^(.*): required version not uniquely present in the submitted file; transitive coverage may be incomplete\.$/,
      "$1: нужная версия не определена однозначно в файле. Транзитивные зависимости проверены не полностью."],
    [/^(.*): no eligible newer stable wheel release for this strategy and Python version\.$/,
      "$1: для этой стратегии и версии Python нет подходящего стабильного wheel-релиза."],
    [/^(.*): this release was not found on PyPI; vulnerability lookup was skipped\.$/,
      "$1: версия не найдена в PyPI. Проверка уязвимостей пропущена."],
    [/^(.*): PyPI metadata unavailable; exact uploaded pin remains unverified\.$/,
      "$1: метаданные PyPI недоступны. Существование указанной версии не подтверждено."],
    [/^(.*): (.*); independent metadata cross-check unavailable\.$/,
      "$1: независимая сверка метаданных недоступна ($2)."],
    [/^(.*): EPSS probabilities remain unknown\.$/, "$1: данные EPSS недоступны."],
    [/^(.*): known exploitation status remains unknown\.$/, "$1: данные CISA KEV недоступны."],
    [/^(.*): advisory details could not be retrieved\.$/, "$1: описание уязвимости недоступно."],
    [/^(.*)\. Vulnerability lookup is incomplete; an empty findings list is not a clean result\.$/,
      "$1. Проверка уязвимостей не завершена. Пустой результат не означает отсутствие риска."],
    [/^Impact component: (.*)\/50 from CVSS (.*)\.$/, "CVSS $2 добавляет $1 из 50 баллов."],
    [/^FIRST EPSS (.*) contributes (.*)\/20; EPSS predicts CVE exploitation in the wild\.$/,
      "EPSS $1 добавляет $2 из 20 баллов. Это оценка вероятности эксплуатации CVE."],
  ];

  for (const [pattern, replacement] of translations) {
    if (pattern.test(message)) return message.replace(pattern, replacement);
  }
  return message.replaceAll("\u2014", ",");
}

export const statusLabel = (status: string) => ({
  queued: "В очереди",
  running: "Проверяется",
  completed: "Завершено",
  succeeded: "Завершено",
  partial: "Неполные данные",
  failed: "Ошибка",
  pending: "Ожидание",
  retry: "Повторная попытка",
  confirmed: "Совпадение",
  possible: "Возможное совпадение",
  no_match: "Совпадений нет",
  insufficient_data: "Недостаточно данных",
  open: "Открыта",
  investigating: "На проверке",
  accepted: "Риск принят",
  resolved: "Закрыта",
  version_match: "Совпадение версии",
}[status] || status);
