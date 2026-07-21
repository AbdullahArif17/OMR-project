import type { Metadata } from "next";
import type { ReactNode } from "react";

// The admin console is unlinked and must never be indexed or previewed.
export const metadata: Metadata = {
  title: "Admin console",
  robots: { index: false, follow: false, nocache: true },
};

export default function AdminLayout({ children }: { children: ReactNode }) {
  return children;
}
