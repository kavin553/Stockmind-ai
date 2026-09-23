import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StockMind AI — Dead Stock Recovery",
  description:
    "Multi-agent dead stock recovery platform: detect aging inventory, evaluate four recovery strategies, and clear it with the least possible loss.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
