import type { Metadata } from "next";
import { IBM_Plex_Mono, Manrope } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { Providers } from "@/components/providers";

const displaySans = Manrope({
  variable: "--font-geist-sans",
  subsets: ["latin", "latin-ext"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Amonora Control",
  description: "Operational control center for Amonora",
  icons: {
    icon: "data:image/svg+xml,%3Csvg%20width%3D%22128%22%20height%3D%22128%22%20viewBox%3D%220%200%20128%20128%22%20fill%3D%22none%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%0A%20%20%3Crect%20width%3D%22128%22%20height%3D%22128%22%20rx%3D%2236%22%20fill%3D%22url%28%23paint0_linear_110_2%29%22%2F%3E%0A%20%20%3Cpath%20d%3D%22M63.9999%2025L95%20100H79.12L72.64%2083.44H55.2L48.88%20100H33L63.9999%2025ZM69.12%2071.04L63.84%2057.04L58.56%2071.04H69.12Z%22%20fill%3D%22white%22%2F%3E%0A%20%20%3Cdefs%3E%0A%20%20%20%20%3ClinearGradient%20id%3D%22paint0_linear_110_2%22%20x1%3D%2214%22%20y1%3D%2210%22%20x2%3D%22116%22%20y2%3D%22118%22%20gradientUnits%3D%22userSpaceOnUse%22%3E%0A%20%20%20%20%20%20%3Cstop%20stop-color%3D%22%232563EB%22%2F%3E%0A%20%20%20%20%20%20%3Cstop%20offset%3D%221%22%20stop-color%3D%22%2306B6D4%22%2F%3E%0A%20%20%20%20%3C%2FlinearGradient%3E%0A%20%20%3C%2Fdefs%3E%0A%3C%2Fsvg%3E",
    shortcut: "data:image/svg+xml,%3Csvg%20width%3D%22128%22%20height%3D%22128%22%20viewBox%3D%220%200%20128%20128%22%20fill%3D%22none%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%0A%20%20%3Crect%20width%3D%22128%22%20height%3D%22128%22%20rx%3D%2236%22%20fill%3D%22url%28%23paint0_linear_110_2%29%22%2F%3E%0A%20%20%3Cpath%20d%3D%22M63.9999%2025L95%20100H79.12L72.64%2083.44H55.2L48.88%20100H33L63.9999%2025ZM69.12%2071.04L63.84%2057.04L58.56%2071.04H69.12Z%22%20fill%3D%22white%22%2F%3E%0A%20%20%3Cdefs%3E%0A%20%20%20%20%3ClinearGradient%20id%3D%22paint0_linear_110_2%22%20x1%3D%2214%22%20y1%3D%2210%22%20x2%3D%22116%22%20y2%3D%22118%22%20gradientUnits%3D%22userSpaceOnUse%22%3E%0A%20%20%20%20%20%20%3Cstop%20stop-color%3D%22%232563EB%22%2F%3E%0A%20%20%20%20%20%20%3Cstop%20offset%3D%221%22%20stop-color%3D%22%2306B6D4%22%2F%3E%0A%20%20%20%20%3C%2FlinearGradient%3E%0A%20%20%3C%2Fdefs%3E%0A%3C%2Fsvg%3E",
    apple: "data:image/svg+xml,%3Csvg%20width%3D%22128%22%20height%3D%22128%22%20viewBox%3D%220%200%20128%20128%22%20fill%3D%22none%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%0A%20%20%3Crect%20width%3D%22128%22%20height%3D%22128%22%20rx%3D%2236%22%20fill%3D%22url%28%23paint0_linear_110_2%29%22%2F%3E%0A%20%20%3Cpath%20d%3D%22M63.9999%2025L95%20100H79.12L72.64%2083.44H55.2L48.88%20100H33L63.9999%2025ZM69.12%2071.04L63.84%2057.04L58.56%2071.04H69.12Z%22%20fill%3D%22white%22%2F%3E%0A%20%20%3Cdefs%3E%0A%20%20%20%20%3ClinearGradient%20id%3D%22paint0_linear_110_2%22%20x1%3D%2214%22%20y1%3D%2210%22%20x2%3D%22116%22%20y2%3D%22118%22%20gradientUnits%3D%22userSpaceOnUse%22%3E%0A%20%20%20%20%20%20%3Cstop%20stop-color%3D%22%232563EB%22%2F%3E%0A%20%20%20%20%20%20%3Cstop%20offset%3D%221%22%20stop-color%3D%22%2306B6D4%22%2F%3E%0A%20%20%20%20%3C%2FlinearGradient%3E%0A%20%20%3C%2Fdefs%3E%0A%3C%2Fsvg%3E",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body className={`${displaySans.variable} ${plexMono.variable} bg-background antialiased`}>
        <Script
          id="amonora-theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html:
              "try{var t=localStorage.getItem('amonora-dashboard-theme')||'dark';document.documentElement.classList.toggle('dark',t==='dark');document.documentElement.dataset.theme=t;}catch(e){document.documentElement.classList.add('dark');document.documentElement.dataset.theme='dark';}",
          }}
        />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
