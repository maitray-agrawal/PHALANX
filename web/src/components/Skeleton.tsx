import React from "react";

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string;
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  width = "100%",
  height = "20px",
  borderRadius = "var(--radius-sm)",
  className = "",
}) => {
  return (
    <div
      className={`skeleton-shimmer ${className}`.trim()}
      style={{
        width,
        height,
        borderRadius,
      }}
      aria-hidden="true"
    />
  );
};

