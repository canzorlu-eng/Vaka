import React from "react";

// Visual language: solid fills with subtle elevation (see .game-btn in index.css).
const VARIANTS = {
  primary: { background: "var(--primary)", color: "#fff" },
  secondary: { background: "var(--secondary)", color: "#fff" },
  accent: { background: "var(--accent)", color: "var(--accent-fg)", borderColor: "var(--border)" },
  ghost: { background: "#fff", color: "var(--fg)", borderColor: "var(--border)" },
  danger: { background: "var(--coral)", color: "#fff" },
};

export const GameButton = ({ variant = "primary", className = "", children, style = {}, type = "button", ...props }) => {
  const v = VARIANTS[variant] || VARIANTS.primary;
  return (
    <button type={type} className={`game-btn px-6 py-3 text-base ${className}`} style={{ ...v, ...style }} {...props}>
      {children}
    </button>
  );
};
