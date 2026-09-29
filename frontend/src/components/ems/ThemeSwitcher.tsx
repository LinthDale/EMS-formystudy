/**
 * ThemeSwitcher（PRD-0005 §6.4：使用者可切換配色主題）。
 *
 * - 由註冊表 driven（styles/themes.ts）：要新增主題 = 加一筆 registry + tokens.css
 *   一段覆寫區塊，本元件零改動。
 * - 選擇即執行期套用 `data-ems-theme` + 持久化 localStorage（lib/theme-preference）。
 * - a11y：原生 <select>（鍵盤可達、有關聯 label）；視覺值全部來自 tokens.css。
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { applyThemePreference, loadThemePreference } from "@/lib/theme-preference";
import { EMS_THEMES } from "@/styles/themes";

export interface ThemeSwitcherProps {
  className?: string;
}

export function ThemeSwitcher({ className }: ThemeSwitcherProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string>(() => loadThemePreference());

  function handleChange(event: React.ChangeEvent<HTMLSelectElement>) {
    setSelected(applyThemePreference(event.target.value));
  }

  return (
    <label
      className={cn(
        "inline-flex items-center gap-2 text-sm text-fg-secondary",
        className,
      )}
    >
      <span className="whitespace-nowrap">{t("theme.label")}</span>
      <select
        value={selected}
        onChange={handleChange}
        aria-label={t("theme.label")}
        className={cn(
          "h-9 rounded-md border border-line bg-surface-raised px-3 text-sm text-fg",
          "transition-colors duration-[var(--ems-motion-duration-fast)] ease-standard",
          "hover:border-line-strong",
        )}
      >
        {EMS_THEMES.map((theme) => (
          <option key={theme.id} value={theme.id}>
            {t(theme.labelKey)}
          </option>
        ))}
      </select>
    </label>
  );
}
