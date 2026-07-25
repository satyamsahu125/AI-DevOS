export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Aurora color system — replaces generic blue
        aurora: {
          purple: "#7C3AED", // primary actions
          violet: "#8B5CF6", // hover state
          cyan: "#06B6D4", // highlights + links
          emerald: "#10B981", // success + approved
          rose: "#F43F5E", // error + destructive
          amber: "#F59E0B", // warning + processing
          muted: "#6B7280", // secondary text
        },
        // Glass surface system
        glass: {
          DEFAULT: "rgba(255, 255, 255, 0.05)",
          hover: "rgba(255, 255, 255, 0.08)",
          border: "rgba(255, 255, 255, 0.10)",
          strong: "rgba(255, 255, 255, 0.12)",
        },
      },
      backgroundImage: {
        // Aurora gradient for accents
        aurora: "linear-gradient(135deg, #7C3AED 0%, #06B6D4 50%, #10B981 100%)",
        "aurora-subtle": "linear-gradient(135deg, rgba(124,58,237,0.15) 0%, rgba(6,182,212,0.15) 100%)",
        "aurora-text": "linear-gradient(135deg, #8B5CF6, #06B6D4)",
        // Dark background layers
        "surface-1": "rgba(10, 10, 20, 1)", // deepest
        "surface-2": "rgba(15, 15, 28, 1)", // cards
        "surface-3": "rgba(20, 20, 35, 1)", // hover
      },
      backdropBlur: {
        glass: "12px",
        "glass-lg": "20px",
      },
      animation: {
        "pulse-slow": "pulse 3s ease-in-out infinite",
        shimmer: "shimmer 2s linear infinite",
        float: "float 6s ease-in-out infinite",
        glow: "glow 2s ease-in-out infinite alternate",
        "fade-up": "fadeUp 0.4s ease-out",
        "slide-right": "slideRight 0.3s ease-out",
        "stage-complete": "stageComplete 0.5s ease-out",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-8px)" },
        },
        glow: {
          "0%": { boxShadow: "0 0 5px rgba(124,58,237,0.3)" },
          "100%": { boxShadow: "0 0 20px rgba(124,58,237,0.7)" },
        },
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideRight: {
          "0%": { opacity: "0", transform: "translateX(-12px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        stageComplete: {
          "0%": { transform: "scale(0.8)", opacity: "0" },
          "60%": { transform: "scale(1.1)" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
      },
      boxShadow: {
        glass: "0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.08)",
        "glass-lg": "0 8px 40px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.10)",
        aurora: "0 0 30px rgba(124,58,237,0.25), 0 0 60px rgba(6,182,212,0.10)",
        "glow-purple": "0 0 20px rgba(124,58,237,0.4)",
        "glow-cyan": "0 0 20px rgba(6,182,212,0.4)",
      },
    },
  },
}
