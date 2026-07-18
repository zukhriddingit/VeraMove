import type { PropsWithChildren } from "react";
import { Link } from "react-router-dom";

export function Layout({ children }: PropsWithChildren) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-teal/15 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <Link className="text-xl font-bold text-ink" to="/">
            VeraMove
          </Link>
          <span className="rounded-full bg-mint px-3 py-1 text-sm font-semibold text-teal">Demo mode</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
    </div>
  );
}
