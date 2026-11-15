import type { NextConfig } from "next";

export default {
  output: "export",
  distDir: process.env.KNOTDEVT_NEXT_DIST_DIR || ".next",
  devIndicators: false,
  agentRules: false,
} satisfies NextConfig;
