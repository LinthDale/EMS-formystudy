/**
 * FontSwitcher（PRD-0005 §6.4：可調整字體控制 — 後臺可切換內文字體）。
 *
 * - 由註冊表 driven（styles/fonts.ts）：要新增字體 = 加一筆 registry，本元件零改動。
 * - 選擇即執行期套用 --ems-font-sans + 持久化 localStorage（lib/font-preference）。
 * - a11y：原生 <select>（鍵盤可達、有關聯 label）；視覺值全部來自 tokens.css。
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { applyFontPreference, loadFontPreference } from "@/lib/font-preference";
import { sansFonts } from "@/styles/fonts";

export interface FontSwitcherProps {
  className?: string;
}

export function FontSwitcher({ className }: FontSwitcherProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string>(() => loadFontPreference());
  const options = sansFonts();

  function handleChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const id = applyFontPreference(event.target.value);
    setSelected(id);
  }

  return (
    <label
      className={cn(
        "inline-flex items-center gap-2 text-sm text-fg-secondary",
        className,
      )}
    >
      <span className="whitespace-nowrap">{t("typography.fontLabel")}</span>
      <select
        value={selected}
        onChange={handleChange}
        className={cn(
          "h-9 rounded-md border border-line bg-surface-raised px-3 text-sm text-fg",
          "transition-colors duration-[var(--ems-motion-duration-fast)] ease-standard",
          "hover:border-line-strong",
        )}
      >
        {options.map((font) => (
          <option key={font.id} value={font.id}>
            {font.label}
          </option>
        ))}
      </select>
    </label>
  );
}
