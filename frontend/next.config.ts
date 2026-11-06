import type { NextConfig } from "next";

// All AI and flight logic lives in the FastAPI backend.
// The browser calls /api/*, which Next proxies to the backend.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  devIndicators: false,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
