import React from "react";

export interface PhalanxLogoProps {
  size?: number;
  className?: string;
  variant?: "primary" | "monochrome" | "dark" | "sandstone";
  withGuideCircle?: boolean;
}

/**
 * Geometric PHALANX Shield Mark.
 * Exact mathematical grammar based on 0/90 degree geometry from
 * the Phalanx Brand Identity Styleboard:
 * - 01: Center Bindu (18x18 diamond)
 * - 02: Protective Shield Form (0/90 sharp cuts)
 * - 03: Financial Nodes (10x10 diamond nodes)
 * - 04: Directional Axis (Vertical spear/guard line)
 */
export const PhalanxMark: React.FC<PhalanxLogoProps> = ({
  size = 48,
  className = "",
  variant = "primary",
  withGuideCircle = false,
}) => {
  // Variant palette mapping
  const colors = {
    primary: {
      shield: "#1E3A8A", // Deep Blue
      inner: "#0EA5A3",  // Teal accent
      spear: "#B87333",  // Copper
      bindu: "#B87333",  // Copper center diamond
      highlight: "#FDF7EC",
    },
    monochrome: {
      shield: "currentColor",
      inner: "currentColor",
      spear: "currentColor",
      bindu: "currentColor",
      highlight: "transparent",
    },
    dark: {
      shield: "#1E3A8A",
      inner: "#0EA5A3",
      spear: "#D9822B",
      bindu: "#D9822B",
      highlight: "#FDF7EC",
    },
    sandstone: {
      shield: "#B87333",
      inner: "#221B14",
      spear: "#221B14",
      bindu: "#221B14",
      highlight: "#EADCC8",
    },
  }[variant];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 192 192"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="PHALANX Seal"
    >
      {/* 05: Guide Circle (Dashed, subtle) */}
      {withGuideCircle && (
        <circle
          cx="96"
          cy="96"
          r="84"
          stroke={colors.spear}
          strokeWidth="1"
          strokeDasharray="4 4"
          opacity="0.3"
        />
      )}

      {/* Lateral Cross Axis with Nodes */}
      <line
        x1="24"
        y1="96"
        x2="168"
        y2="96"
        stroke={colors.spear}
        strokeWidth="1.25"
        opacity="0.6"
      />
      {/* West Node */}
      <polygon points="24,91 29,96 24,101 19,96" fill={colors.spear} />
      {/* East Node */}
      <polygon points="168,91 173,96 168,101 163,96" fill={colors.spear} />

      {/* 04: Directional Axis (Vertical Spear of Control & Oversight) */}
      <line
        x1="96"
        y1="12"
        x2="96"
        y2="180"
        stroke={colors.spear}
        strokeWidth="1.5"
      />
      {/* North Spearhead Diamond */}
      <polygon points="96,12 102,22 96,32 90,22" fill={colors.spear} />
      {/* South Base Diamond */}
      <polygon points="96,160 102,170 96,180 90,170" fill={colors.spear} />

      {/* 02: Protective Shield Form (0/90 Geometry) */}
      {/* Left Outer Shield Wing */}
      <path
        d="M96 46 L38 60 L62 126 L96 162 L82 122 L62 76 Z"
        fill={colors.shield}
      />
      {/* Right Outer Shield Wing */}
      <path
        d="M96 46 L154 60 L130 126 L96 162 L110 122 L130 76 Z"
        fill={colors.shield}
      />

      {/* Inner Chevron / Shield Guard Plates */}
      <path
        d="M96 66 L68 76 L82 118 L96 140 L96 112 L84 88 Z"
        fill={colors.inner}
        opacity="0.9"
      />
      <path
        d="M96 66 L124 76 L110 118 L96 140 L96 112 L108 88 Z"
        fill={colors.inner}
        opacity="0.9"
      />

      {/* 01: Center Bindu (Core 18x18 Diamond) */}
      <polygon
        points="96,78 114,96 96,114 78,96"
        fill={colors.bindu}
      />
      {/* Inner Core Accent */}
      <polygon
        points="96,86 106,96 96,106 86,96"
        fill={colors.highlight}
      />

      {/* 03: Upper Diamond Nodes */}
      <polygon points="56,66 61,71 56,76 51,71" fill={colors.spear} />
      <polygon points="136,66 141,71 136,76 131,71" fill={colors.spear} />
    </svg>
  );
};

export interface PhalanxHeaderBrandProps {
  size?: number;
  showTagline?: boolean;
}

export const PhalanxHeaderBrand: React.FC<PhalanxHeaderBrandProps> = ({
  size = 40,
  showTagline = true,
}) => {
  return (
    <div className="phalanx-brand-lockup">
      <PhalanxMark size={size} />
      <div className="phalanx-brand-text">
        <div className="phalanx-brand-row">
          <span className="phalanx-title">PHALANX</span>
          <span className="phalanx-system-badge">ASTRAX INTELLIGENCE</span>
        </div>
        {showTagline && (
          <span className="phalanx-subtitle">
            AGENT PAYMENTS UNDER CONTROL
          </span>
        )}
      </div>
    </div>
  );
};
