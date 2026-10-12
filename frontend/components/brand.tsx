import Link from "next/link";

export function Mark({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" clipRule="evenodd" d="M8 6h17l8 8v4l-8 8h-9v9H8V6Zm8 6v8h7l4-4-4-4h-7Z" />
    </svg>
  );
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className={`brand${compact ? " brand-compact" : ""}`} href="/" aria-label="PAXVEIL, главная">
      <Mark />
      <span>PAXVEIL</span>
    </Link>
  );
}
