/**
 * i18n — zh-Hant（FR-531：中文在地化為主）
 * 所有操作字串集中於此；元件不得硬編中文字串。
 */
export const zhHant = {
  common: {
    appName: "SynaIQ EMS",
    appTagline: "能源管理平台",
    loadMore: "載入更多",
    retry: "重試",
    noData: "無資料",
  },
  device: {
    status: {
      candidate: "候選",
      confirmed: "已確認",
      active: "運轉中",
      retired: "已退役",
      unknown: "未知狀態",
      stale: "過時",
    },
  },
  confidence: {
    label: "AI 分類信心",
    unclassified: "未分類",
    band: { low: "低", medium: "中", high: "高" },
  },
  measurement: {
    updatedAt: "更新於",
    noValue: "—",
    domain: { electricity: "電力", factory: "工廠" },
  },
  review: {
    title: "AI 審閱摘要",
    source: { llm: "AI 產生", system_fallback: "系統備援", unknown: "來源不明" },
    provider: "提供者",
    model: "模型",
    promptVersion: "Prompt 版本",
    generatedAt: "產生時間",
    plainTextNote: "摘要以純文字呈現（XSS 防護 §9.5）",
  },
  signal: {
    sparklineLabel: "{{name}} 趨勢",
    insufficientData: "資料不足",
  },
  deviceTable: {
    caption: "設備清單",
    empty: "目前沒有符合條件的設備",
    shown: "顯示 {{shown}} / {{total}} 台",
    headers: {
      deviceId: "設備編號",
      deviceType: "類型",
      status: "狀態",
      aiConfidence: "AI 信心",
      lastSeenAt: "最後上線",
    },
    sortBy: "依{{column}}排序",
  },
  gallery: {
    title: "EMS Design System 元件展示",
    subtitle: "PRD-0005 §6.4 — Precise / Industrial / Alive（P1 design 驗收 gate 截圖頁）",
    sections: {
      statusPill: "設備狀態徽章 DeviceStatusPill",
      confidenceMeter: "AI 信心量表 ConfidenceMeter",
      measurementCard: "即時量測卡片 MeasurementCard",
      sparkline: "Signal 迷你趨勢 SignalSparkline",
      reviewDigest: "AI 審閱摘要 ReviewDigestPanel",
      deviceTable: "設備清單 DeviceTable",
      chartTheme: "ECharts 主題（charts/theme.ts）",
    },
    chartDemoTitle: "近 24 小時功率（mock）",
  },
} as const;

export type Messages = typeof zhHant;
