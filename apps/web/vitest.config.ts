import { defineConfig } from "vitest/config";

// Minimal Vitest setup: jsdom gives us window/localStorage so the api client
// (which reads a token from localStorage) runs as it does in the browser.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["**/*.test.ts", "**/*.test.tsx"],
  },
});
