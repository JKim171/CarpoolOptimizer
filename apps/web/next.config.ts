import path from "node:path";

import type { NextConfig } from "next";

import { PRIVATE_PATH_PREFIX } from "./lib/seo";

const nextConfig: NextConfig = {
  // This app lives in a repository whose root holds a Python project, so Next's automatic root
  // detection walks up past `apps/web` and warns. Pinning it keeps the build reading only this
  // directory's lockfile.
  turbopack: { root: path.resolve(__dirname) },

  /**
   * The second of the two guards keeping event pages out of search indexes.
   *
   * The first is `robots: { index: false }` in `app/events/[publicId]/layout.tsx`. This one says the
   * same thing in a response header, which is independent of React rendering entirely: it still
   * applies if that metadata export is lost in a refactor, and it covers responses a crawler might
   * see without executing or parsing the document body.
   *
   * Event URLs carry the event's `public_id` and the page renders participants' home addresses
   * (CLAUDE.md), so this is worth saying twice. `app/robots.ts` disallows the same paths, but
   * `robots.txt` only asks a crawler not to fetch -- a URL discovered elsewhere, such as a link an
   * organizer pastes somewhere public, can still be indexed from that link alone. `noindex` is what
   * answers that case, and it has to be on the response.
   */
  async headers() {
    return [
      {
        source: `${PRIVATE_PATH_PREFIX}/:path*`,
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
    ];
  },
};

export default nextConfig;
