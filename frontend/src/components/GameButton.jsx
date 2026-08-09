import React from "react";

const VARIANTS = {
  primary: { background: "var(--primary)", color: "#fff", "--shadow-btn": "#E0705A" },
  secondary: { background: "var(--secondary)", color: "#fff", "--shadow-btn": "#5FA184" },
  accent: { background: "var(--accent)", color: "var(--accent-fg)", "--shadow-btn": "#D9CBBA" },
  ghost: { background: "#fff", color: "var(--fg)", "--shadow-btn": "#EAE2D8" },
  danger: { background: "#E8705B", color: "#fff", "--shadow-btn": "#C2543F" },
};

export const GameButton = ({ variant = "primary", className = "", children, style = {}, ...props }) => {
  const v = VARIANTS[variant] || VARIANTS.primary;
  return (
    <button
      className={`game-btn px-6 py-3 text-base ${className}`}
      style={{ ...v, ...style }}
      {...props}
    >
      {children}
    </button>
  );
};
