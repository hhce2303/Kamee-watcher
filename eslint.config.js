import js from "@eslint/js";
import tseslint from "typescript-eslint";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import globals from "globals";

export default tseslint.config(
  {
    ignores: ["dist/**", "src-tauri/**", "node_modules/**", "src/types/dto.gen.ts"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  react.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
    },
    languageOptions: {
      ...react.configs.flat.recommended.languageOptions,
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: "detect" },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // React 18 + the automatic JSX runtime: no need to import React itself.
      "react/react-in-jsx-scope": "off",
      "react/jsx-uses-react": "off",
      // TypeScript already enforces prop shapes.
      "react/prop-types": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // The codebase intentionally keeps some IPC/event payloads loosely typed
      // at the boundary — flag as a warning to fix over time, not a hard error.
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "src/test/**/*.{ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, ...globals.jest },
    },
  },
  {
    files: ["*.config.{js,ts}", "scripts/**/*.js"],
    languageOptions: {
      globals: globals.node,
    },
  },
);
