export type Theme = "light" | "dark" | "system";

const KEY = "dt_theme";

export function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "system";
  try {
    return (window.localStorage.getItem(KEY) as Theme) || "system";
  } catch {
    return "system";
  }
}

export function resolveDark(theme: Theme): boolean {
  if (theme === "dark") return true;
  if (theme === "light") return false;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", resolveDark(theme));
}

export function setTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(KEY, theme);
  } catch {
    /* ignore */
  }
  applyTheme(theme);
}

// Inline script (stringified) run before paint to avoid a flash of the wrong theme.
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('dt_theme')||'system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;
