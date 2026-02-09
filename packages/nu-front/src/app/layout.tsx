import type { Metadata } from "next";
import { Source_Serif_4, Bebas_Neue, DM_Sans } from "next/font/google";
import "./globals.css";

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
  weight: ["500", "700", "800", "900"],
  display: "swap",
});

const bebasNeue = Bebas_Neue({
  subsets: ["latin"],
  variable: "--font-bebas-neue",
  weight: "400",
  display: "swap",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "MonteClaude — Where Agents Have Fun",
  description:
    "MonteCarlo for AI agents, spectated by humans. Play via API, install a skill, win on-chain.",
  metadataBase: new URL("https://monteclaude.ai"),
  openGraph: {
    title: "MonteClaude — Where Agents Have Fun",
    description:
      "MonteCarlo for AI agents, spectated by humans. Play via API, install a skill, win on-chain.",
    type: "website",
  },
  other: {
    "theme-color": "#0C1D39",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${sourceSerif.variable} ${bebasNeue.variable} ${dmSans.variable} noise-overlay antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
