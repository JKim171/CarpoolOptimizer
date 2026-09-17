import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // This app lives in a repository whose root holds a Python project, so Next's automatic root
  // detection walks up past `apps/web` and warns. Pinning it keeps the build reading only this
  // directory's lockfile.
  turbopack: { root: path.resolve(__dirname) },
};

export default nextConfig;
