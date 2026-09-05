import { FlatCompat } from "@eslint/eslintrc";
import simpleImportSort from "eslint-plugin-simple-import-sort";
import unusedImports from "eslint-plugin-unused-imports";
import { dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  // Ignore auto-generated hey-api client files
  // .next/ is build output. Without this, running fix-lint after a local
  // `next build` lints ~50k lines of generated bundle and buries any real
  // finding. CI never hit it because format.sh runs before anything builds.
  // next-env.d.ts is generated too, and gains a triple-slash reference to
  // .next/types only once a build has run.
  { ignores: [".next/", "next-env.d.ts", "src/client/client/", "src/client/core/", "src/client/client.gen.ts", "src/client/sdk.gen.ts", "src/client/types.gen.ts", "src/client/index.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    plugins: {
      "simple-import-sort": simpleImportSort,
      "unused-imports": unusedImports,
    },
    rules: {
      /* formatting / layout */
      "no-multiple-empty-lines": ["error", { max: 2, maxBOF: 1, maxEOF: 1 }],
      "eol-last": ["error", "always"],
      "no-trailing-spaces": "error",

      /* imports */
      "simple-import-sort/imports": "error",
      "simple-import-sort/exports": "error",
      "unused-imports/no-unused-imports": "error",
      "unused-imports/no-unused-vars": ["warn", { vars: "all", args: "after-used" }],

    },
    languageOptions: {
      sourceType: "module",
      ecmaVersion: "latest"
    }
  }
];

export default eslintConfig;
