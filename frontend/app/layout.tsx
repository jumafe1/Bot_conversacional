import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Rappi Data Bot",
  description:
    "Chat in plain Spanish or English to query Rappi's operational metrics across 9 LATAM markets.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-ink-50 text-ink-900">{children}</body>
    </html>
  );
}
