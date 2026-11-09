import next from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const config = [
  ...next,
  ...typescript,
  { ignores: [".next/**", "out/**", "next-env.d.ts", "src/api-schema.ts"] },
];

export default config;
