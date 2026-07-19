import { Link, useLocation, useRouter } from "@tanstack/react-router";
import { ShieldCheck, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { isDemoMode } from "@/lib/api";
import { RuntimeModeBadge } from "./RuntimeModeBadge";
import { HealthIndicator } from "./HealthIndicator";
import { JourneyStepper } from "./JourneyStepper";
import { Button } from "@/components/ui/button";

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { pathname } = useLocation();
  const onLanding = pathname === "/";

  const resetDemo = () => {
    qc.clear();
    router.navigate({ to: "/" });
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-4 py-3 md:px-8">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ShieldCheck className="h-4 w-4" />
            </span>
            <span className="text-base">
              Vera<span className="text-verified">Move</span>
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <HealthIndicator />
            <RuntimeModeBadge />
            {isDemoMode && !onLanding && (
              <Button
                variant="ghost"
                size="sm"
                onClick={resetDemo}
                className="gap-1.5 text-muted-foreground"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reset demo
              </Button>
            )}
          </div>
        </div>
        {!onLanding && (
          <div className="mx-auto max-w-[1240px] px-4 pb-3 md:px-8">
            <JourneyStepper />
          </div>
        )}
      </header>
      <main className="mx-auto max-w-[1240px] px-4 py-8 md:px-8 md:py-12">
        {children}
      </main>
      <footer className="mx-auto max-w-[1240px] px-4 pb-10 pt-6 text-xs text-muted-foreground md:px-8">
        VeraMove operates independently today and is designed as a future move-in
        concierge for VeraAI.
      </footer>
    </div>
  );
}
