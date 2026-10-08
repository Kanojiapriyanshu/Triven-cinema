import type { NextConfig } from "next";

const internalApi = process.env.TRIVEN_INTERNAL_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Ship only traced runtime dependencies in the production container.
  output: "standalone",
  // A second dev server (for previews/tests) needs its own build folder.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  poweredByHeader: false,
  compress: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApi}/api/:path*`,
      },
      {
        source: "/media/:path*",
        destination: `${internalApi}/media/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
