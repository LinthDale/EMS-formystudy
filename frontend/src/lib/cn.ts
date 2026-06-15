import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn 慣例的 class 合併 helper（components.json aliases.utils 指向此檔） */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
