import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EarthScope | Environmental Intelligence",
  description: "Explore environmental change across Ghana through climate data, geospatial evidence and statistical trend analysis.",
  applicationName: "EarthScope"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
