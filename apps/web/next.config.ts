import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async redirects() {
    return [{ source: "/skills", destination: "/tools", permanent: false }];
  },
};

export default nextConfig;
