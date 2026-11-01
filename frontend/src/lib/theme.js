import { useEffect, useState } from "react";

// "system" follows the OS setting; "light" / "dark" are explicit choices stored per browser.
const KEY = "veriqo_theme";
export const THEMES = ["light", "dark", "system"];

export function getStoredTheme() {
  try {
    const t = localStorage.getItem(KEY);
    return THEMES.includes(t) ? t : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export function useTheme() {
  const [theme, setTheme] = useState(getStoredTheme);
  useEffect(() => {
    applyTheme(theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* storage blocked: the choice lasts for this page load */
    }
  }, [theme]);
  return [theme, setTheme];
}
