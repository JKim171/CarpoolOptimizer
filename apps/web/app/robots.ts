/**
 * `robots.txt`, generated rather than written as a static file so it reads the same constants the
 * rest of the app does.
 *
 * `Disallow` is a request not to *fetch*, which is a weaker thing than `noindex` and is not what
 * keeps event pages out of search results -- a URL linked from somewhere public can be indexed
 * without ever being fetched. The `noindex` in `app/events/[publicId]/layout.tsx` and the
 * `X-Robots-Tag` in `next.config.ts` are what do that. This is here so a well-behaved crawler does
 * not request pages holding home addresses in the first place.
 */

import type { MetadataRoute } from "next";

import { PRIVATE_PATH_PREFIX, SITE_URL } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: `${PRIVATE_PATH_PREFIX}/`,
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
