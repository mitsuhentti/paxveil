import Link from "next/link";
export function Mark({ size = 34 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M20 3 35 11.5v17L20 37 5 28.5v-17L20 3Z" stroke="currentColor" strokeWidth="1.5"/><path d="m12 14 8-4 8 4v12l-8 4-8-4V14Zm8-4v10m-8-6 8 6 8-6m-8 6v10" stroke="currentColor" strokeWidth="1.5"/><circle cx="20" cy="20" r="3" fill="currentColor"/></svg>;
}
export function Brand({ compact = false }: { compact?: boolean }) { return <Link className="brand" href="/" aria-label="PAXVEIL — главная"><Mark /><span>PAXVEIL{!compact && <small>DEPENDENCY INTELLIGENCE</small>}</span></Link>; }
