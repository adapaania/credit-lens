import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CreditLens",
  description: "Cited SEC filing Q&A for credit analysts",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
