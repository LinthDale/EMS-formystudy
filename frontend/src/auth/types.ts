/**
 * Auth 型別（PRD-0005 §9.1）— 對齊 LIVE BFF roles（services/bff/bff/roles.py）。
 *
 * 每個 session 恰帶一個 role；前端 role 僅用於 UX（隱藏/禁用無權操作），
 * 真正權限邊界在 BFF + 後端（§9.1：前端隱藏非安全邊界）。
 */

/** BFF role enum（roles.py：ops / ingest / readonly）。 */
export const KNOWN_ROLES = ["ops", "ingest", "readonly"] as const;

export type Role = (typeof KNOWN_ROLES)[number];

/**
 * 未知 role 收斂為最小權限 'readonly'（open-ended enum 安全預設，§13.2）。
 * 後端新增 role 時前端不致崩潰，且不誤授權。
 */
export function toRole(value: string | null | undefined): Role {
  return (KNOWN_ROLES as readonly string[]).includes(value ?? "")
    ? (value as Role)
    : "readonly";
}

/** 已驗證的 session 摘要（不含任何金鑰/敏感資料）。 */
export interface AuthSession {
  readonly username: string;
  readonly role: Role;
}
