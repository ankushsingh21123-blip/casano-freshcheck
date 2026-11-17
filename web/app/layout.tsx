import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FreshCheck — Stale-Answer Detector",
  description:
    "Check whether a stored AI answer is still fresh, using live Tavily evidence and transparent heuristic signals.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
