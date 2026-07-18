import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#102a2e",
        mint: "#dff7ed",
        teal: "#087f72",
        sand: "#fff9ed",
      },
    },
  },
  plugins: [],
} satisfies Config;
