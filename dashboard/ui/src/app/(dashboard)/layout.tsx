"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { AppShell } from "@/components/app-shell";
import { PageLoader } from "@/components/query-state";
import { useSession } from "@/hooks/use-dashboard";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const session = useSession();

  useEffect(() => {
    if (session.isError) {
      router.replace("/login");
    }
  }, [router, session.isError]);

  if (session.isLoading) {
    return (
      <div className="p-6">
        <PageLoader label="Проверяю сессию администратора..." />
      </div>
    );
  }

  if (!session.data) {
    return null;
  }

  return <AppShell session={session.data}>{children}</AppShell>;
}
