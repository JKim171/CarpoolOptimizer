/**
 * The sitemap: the landing page and the example at `/demo`.
 *
 * That is the honest size of this site's public surface. Everything else is an event page, and
 * those are private by requirement (`lib/seo.ts`).
 *
 * Content pages aimed at what coordinators actually search for are the next piece of work, and each
 * one gets a line here.
 */

import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/seo";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: `${SITE_URL}/`,
      // Build time. The landing page is static, so the build is genuinely the last moment its
      // content could have changed.
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 1,
    },
    {
      url: `${SITE_URL}/demo`,
      // No `lastModified`: the page changes only when `make demo` regenerates it, and a build-time
      // date would claim a change on every deploy.
      changeFrequency: "monthly",
      priority: 0.8,
    },
  ];
}
