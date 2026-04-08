import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Next Move — Outreach Systeem",
  description: "Geautomatiseerd outreach dashboard voor Next Move Marketing",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="nl">
      <body>{children}</body>
    </html>
  );
}
