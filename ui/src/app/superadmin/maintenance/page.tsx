"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { MaintenancePanel } from "./MaintenancePanel";

export default function MaintenancePage() {
  return (
    <main className="container mx-auto max-w-3xl space-y-6 p-6">
      <div className="space-y-1">
        <Link
          href="/superadmin"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Superadmin
        </Link>
        <h1 className="text-2xl font-bold">Server maintenance</h1>
        <p className="text-muted-foreground">
          Keep the server&apos;s disk from filling up.
        </p>
      </div>
      <MaintenancePanel />
    </main>
  );
}
