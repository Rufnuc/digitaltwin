import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DigitalTwin — Business Decision Support",
  description: "AI Business Digital Twin & Decision Support Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans text-ink antialiased">{children}</body>
    </html>
  );
}
