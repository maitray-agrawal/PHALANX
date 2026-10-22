import React, { useEffect, useState } from "react";
import { Sun, Moon, Laptop } from "lucide-react";

export type ThemeMode = "light" | "dark" | "system";

export const ThemeSwitcher: React.FC = () => {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem("phalanx-theme") as ThemeMode | null;
    return saved || "system";
  });

  useEffect(() => {
    const applyTheme = (currentTheme: ThemeMode) => {
      let resolved = currentTheme;
      if (currentTheme === "system") {
        const prefersDark =
          typeof window !== "undefined" && typeof window.matchMedia === "function"
            ? window.matchMedia("(prefers-color-scheme: dark)").matches
            : false;
        resolved = prefersDark ? "dark" : "light";
      }
      if (typeof document !== "undefined") {
        document.documentElement.setAttribute("data-theme", resolved);
      }
      try {
        if (typeof localStorage !== "undefined") {
          localStorage.setItem("phalanx-theme", currentTheme);
        }
      } catch {
        // storage disabled
      }
    };

    applyTheme(theme);

    // If in system mode, listen for OS changes
    if (
      theme === "system" &&
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function"
    ) {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const handleChange = () => applyTheme("system");
      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener("change", handleChange);
        return () => mediaQuery.removeEventListener("change", handleChange);
      }
    }
  }, [theme]);

  return (
    <div className="theme-switcher-container" role="radiogroup" aria-label="Visual Theme">
      <button
        type="button"
        className={`theme-btn ${theme === "light" ? "active" : ""}`}
        onClick={() => setTheme("light")}
        title="Light Mode (AstraX Ivory & Sandstone)"
        aria-checked={theme === "light"}
        role="radio"
      >
        <Sun size={14} />
        <span className="theme-btn-label">Light</span>
      </button>
      <button
        type="button"
        className={`theme-btn ${theme === "dark" ? "active" : ""}`}
        onClick={() => setTheme("dark")}
        title="Dark Mode (Deep Ink & Copper)"
        aria-checked={theme === "dark"}
        role="radio"
      >
        <Moon size={14} />
        <span className="theme-btn-label">Dark</span>
      </button>
      <button
        type="button"
        className={`theme-btn ${theme === "system" ? "active" : ""}`}
        onClick={() => setTheme("system")}
        title="System Preference"
        aria-checked={theme === "system"}
        role="radio"
      >
        <Laptop size={14} />
        <span className="theme-btn-label">System</span>
      </button>
    </div>
  );
};
