import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./node_modules/@assistant-ui/**/*.{js,mjs,cjs}",
  ],
  theme: {
    extend: {
      colors: {
        // Rappi-ish accent (muted, not the screaming brand red).
        brand: {
          50: "#fff5f2",
          100: "#ffe8e2",
          200: "#ffcabd",
          300: "#ffa58f",
          400: "#ff7f60",
          500: "#ff5a34",
          600: "#ea4717",
          700: "#bf3913",
          800: "#8f2d10",
          900: "#66220d",
        },
        ink: {
          50: "#f7f8fa",
          100: "#eef0f4",
          200: "#dcdfe6",
          300: "#b8bec9",
          400: "#8c94a3",
          500: "#62697a",
          600: "#444a58",
          700: "#2e3340",
          800: "#1c2029",
          900: "#11141b",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "monospace"],
      },
      boxShadow: {
        "elev-1": "0 1px 2px rgba(17, 20, 27, 0.05), 0 1px 3px rgba(17, 20, 27, 0.06)",
        "elev-2": "0 4px 12px rgba(17, 20, 27, 0.06), 0 1px 3px rgba(17, 20, 27, 0.04)",
      },
    },
  },
  plugins: [typography],
};

export default config;
