import type { NextConfig } from "next";

const portalApiBase = (
  process.env.PORTAL_API_BASE ||
  process.env.NEXT_PUBLIC_PORTAL_API_BASE ||
  "http://127.0.0.1:5002"
).replace(/\/+$/, "");

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.0.132"],
  async rewrites() {
    return [
      {
        source: "/portal/:path*",
        destination: `${portalApiBase}/portal/:path*`,
      },
    ];
  },
};

export default nextConfig;
