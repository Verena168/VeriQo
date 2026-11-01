import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "../lib/theme";

const OPTIONS = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
];

/** Three-way segmented switch: Light / Dark / follow the operating system. */
export default function ThemeToggle({ className = "" }) {
  const [theme, setTheme] = useTheme();
  return (
    <div role="radiogroup" aria-label="Colour theme" className={`inline-flex rounded-lg border border-line bg-surface p-0.5 ${className}`}>
      {OPTIONS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          role="radio"
          aria-checked={theme === id}
          title={`${label} theme`}
          onClick={() => setTheme(id)}
          className={`grid size-7 place-items-center rounded-md transition ${
            theme === id ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"
          }`}
        >
          <Icon className="size-4" aria-hidden />
          <span className="sr-only">{label}</span>
        </button>
      ))}
    </div>
  );
}
