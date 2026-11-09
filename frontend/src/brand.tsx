import Link from "next/link";

export function Mark() {
  return (
    <svg viewBox="0 0 36 28" width="32" fill="none" aria-hidden="true">
      <path
        d="M2 19C9 19 10 4 18 4s9 15 16 15M2 9c7 0 8 15 16 15s9-15 16-15"
        stroke="currentColor"
        strokeWidth="2.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Brand() {
  return (
    <Link href="/" className="brand">
      <Mark />
      KnotDevt<span>.</span>
    </Link>
  );
}
