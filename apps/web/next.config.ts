import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next 16 blocks cross-origin dev resources by default (HMR, React dev client
  // chunks, etc). When the browser uses a host that differs from the bind host
  // (e.g. visiting http://127.0.0.1:3000 while the internal server reports
  // localhost, or vice versa, or when accessed via LAN IP), hydration silently
  // fails — the DOM renders but React never attaches event handlers, so buttons
  // and dropdowns stop responding to clicks. Allow the common dev hosts here.
  allowedDevOrigins: [
    "127.0.0.1",
    "localhost",
    "127.0.0.1:3000",
    "localhost:3000",
    "172.24.16.1",
    "172.24.16.1:3000",
  ],
};

export default nextConfig;
