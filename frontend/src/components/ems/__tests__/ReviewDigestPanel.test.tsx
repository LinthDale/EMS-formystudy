/**
 * ReviewDigestPanel（FR-511）：AI digest 審閱。
 * §9.5 [必過]：digest 為 LLM 產出且寫入端可能被 MQTT payload 注入 →
 * 一律純文字渲染（無 innerHTML、無未消毒 markdown→HTML）。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  ReviewDigestPanel,
  flattenDigest,
} from "@/components/ems/ReviewDigestPanel";
import { MOCK_REVIEW_DIGEST } from "@/api/fixtures";
import type { DigestOut } from "@/api/types";

describe("flattenDigest（純函數）", () => {
  it("巢狀物件攤平為 dot-path 文字列", () => {
    const rows = flattenDigest({ a: { b: 1 }, c: "x" });
    expect(rows).toContainEqual({ path: "a.b", text: "1" });
    expect(rows).toContainEqual({ path: "c", text: "x" });
  });

  it("純量陣列以頓號連接", () => {
    const rows = flattenDigest({ warnings: ["w1", "w2"] });
    expect(rows).toContainEqual({ path: "warnings", text: "w1、w2" });
  });

  it("不改變輸入（immutability）", () => {
    const input = { a: { b: 1 } };
    const snapshot = JSON.stringify(input);
    flattenDigest(input);
    expect(JSON.stringify(input)).toBe(snapshot);
  });

  it("超深巢狀以 JSON 字串收斂（防遞迴爆炸，仍為純文字）", () => {
    const deep = { l1: { l2: { l3: { l4: { l5: { l6: "x" } } } } } };
    const rows = flattenDigest(deep);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((r) => typeof r.text === "string")).toBe(true);
  });
});

describe("ReviewDigestPanel", () => {
  it("顯示標題、來源徽章（llm → AI 產生）與 provider/model", () => {
    render(<ReviewDigestPanel review={MOCK_REVIEW_DIGEST} />);
    expect(screen.getByText("AI 審閱摘要")).toBeInTheDocument();
    const badge = screen.getByText("AI 產生");
    expect(badge).toHaveAttribute("data-source", "llm");
    expect(screen.getByText("anthropic")).toBeInTheDocument();
    expect(screen.getByText("claude-sonnet-4-5")).toBeInTheDocument();
  });

  it("system_fallback 來源顯示「系統備援」", () => {
    render(
      <ReviewDigestPanel
        review={{ ...MOCK_REVIEW_DIGEST, summary_source: "system_fallback" }}
      />,
    );
    expect(screen.getByText("系統備援")).toHaveAttribute(
      "data-source",
      "system_fallback",
    );
  });

  it("digest 內容（rationale / warnings）以文字呈現", () => {
    render(<ReviewDigestPanel review={MOCK_REVIEW_DIGEST} />);
    expect(screen.getByText(/室溫一致/)).toBeInTheDocument();
    expect(screen.getByText(/unit 欄位缺漏/)).toBeInTheDocument();
  });

  it("[§9.5 必過] HTML / script 注入一律以字面文字渲染，不產生節點", () => {
    const hostile: DigestOut = {
      device_id: "evil-001",
      summary_source: "llm",
      digest: {
        rationale: '<img src=x onerror="alert(1)">',
        "<script>k</script>": "<script>alert(document.cookie)</script>",
        nested: { html: "<iframe src='https://evil.example'></iframe>" },
      },
    };
    const { container } = render(<ReviewDigestPanel review={hostile} />);
    expect(container.querySelector("script, img, iframe")).toBeNull();
    expect(container.textContent).toContain("<script>alert(document.cookie)</script>");
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
  });
});
