/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: "#09090b", // zinc-950
          card: "#121214", // custom slate-obsidian
          border: "#27272a", // zinc-800
          text: "#f4f4f5", // zinc-100
          "text-muted": "#a1a1aa", // zinc-400
          green: "#10b981", // emerald-500
          blue: "#3b82f6", // blue-500
          cyan: "#06b6d4", // cyan-500
          red: "#ef4444", // red-500
          amber: "#f59e0b", // amber-500
        }
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "Courier New", "monospace"],
        sans: ["Inter", "Outfit", "sans-serif"],
      },
      boxShadow: {
        "glow-green": "0 0 15px rgba(16, 185, 129, 0.15)",
        "glow-red": "0 0 20px rgba(239, 68, 68, 0.25)",
        "glow-cyan": "0 0 15px rgba(6, 182, 212, 0.15)",
        "glow-blue": "0 0 15px rgba(59, 130, 246, 0.15)",
      },
      animation: {
        "pulse-fast": "pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "siren": "siren 1.5s ease-in-out infinite",
        "ping-slow": "ping 2.5s cubic-bezier(0, 0, 0.2, 1) infinite",
        "scan": "scan 4s linear infinite",
      },
      keyframes: {
        siren: {
          "0%, 100%": { backgroundColor: "rgba(239, 68, 68, 0.05)", boxShadow: "0 0 10px rgba(239, 68, 68, 0.1) inset" },
          "50%": { backgroundColor: "rgba(239, 68, 68, 0.2)", boxShadow: "0 0 25px rgba(239, 68, 68, 0.4) inset" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        }
      }
    },
  },
  plugins: [],
}
