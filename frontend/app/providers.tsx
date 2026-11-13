"use client";

import AppShell from "@/components/AppShell";
import { ToastProvider } from "@/components/Toast";
import { AuthProvider } from "@/lib/auth";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <AuthProvider>
        <AppShell>{children}</AppShell>
      </AuthProvider>
    </ToastProvider>
  );
}
