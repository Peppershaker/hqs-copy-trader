import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { WSProvider } from "@/components/layout/ws-provider";
import { ReplayDialog } from "@/components/dashboard/replay-dialog";

export const metadata: Metadata = {
  title: "DAS Copy Trader",
  description: "Semi-automatic copy trading for DAS Trader Pro",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        <WSProvider>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto p-6">{children}</main>
          </div>
          <ReplayDialog />
        </WSProvider>
      </body>
    </html>
  );
}
