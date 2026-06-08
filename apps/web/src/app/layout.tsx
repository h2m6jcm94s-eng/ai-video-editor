// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { validateClientEnv } from "@/lib/env";

validateClientEnv();

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AI Video Editor - Reference Style Matching",
  description: "Parse a reference video's style and apply it to your clips",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
