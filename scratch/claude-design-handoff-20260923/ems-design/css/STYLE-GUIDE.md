# tAIstro EMS CSS 規範

本套件是 Claude Design 畫布七張畫面（`project/*.dc.html`）的**實作契約**：畫面上每個顏色、字級、字重、字距、行高、間距、圓角、線寬、陰影與動態時間，在這裡都有一個權杖（token）與之 1:1 對應。畫布維持 inline 字面值，方便在編輯器中直接修改；正式前端一律改用本套件。

結構比照 synaiq-web：**一個權杖檔放所有數值，一個 app 檔只放版面與元件**，以 BEGIN／END 區塊分段，並用檢查腳本強制執行。

---

## 1. 檔案結構與載入順序

```
css/
├─ ems-tokens.css    權杖：:root { --ems-… }，區段 00–07，每行附用途註解
├─ ems-app.css       版面與元件：BASE → SHELL → CARDS → KPI → CHARTS → TABLES → CONTROLS → STATUS → UTILITIES
├─ css-lint.mjs      規範檢查（無相依套件，Node 18+）
├─ check-css.txt     最近一次檢查結果
└─ STYLE-GUIDE.md    本文件
```

載入順序固定：先權杖、後元件。

```html
<link rel="stylesheet" href="css/ems-tokens.css">
<link rel="stylesheet" href="css/ems-app.css">
```

字型與畫布相同，只用一條 Google Fonts css2 連結：Manrope 400/500、Newsreader（opsz 6–72）300/400、Noto Sans TC 400/500、Noto Serif TC 300/400。

## 2. 命名規則

| 對象 | 規則 | 範例 |
|---|---|---|
| 權杖 | `--ems-<類別>-<名稱>`；第一段即類別 | `--ems-font-size-lg`、`--ems-space-16`、`--ems-radius-card` |
| 色盤 | 以材質命名，不以用途命名 | `--ems-paper`、`--ems-ink`、`--ems-olive`、`--ems-gold` |
| 語意角色 | `--ems-color-<角色>`，只引用色盤 | `--ems-color-text-muted: var(--ems-muted)` |
| 區塊 | `.ems-<block>` | `.ems-card`、`.ems-nav-item` |
| 元素 | `.ems-<block>__<element>` | `.ems-card__title`、`.ems-kpi__value` |
| 修飾 | `.ems-<block>--<modifier>`（元素亦可加修飾） | `.ems-level--p1`、`.ems-kpi__value--hero` |

- 只用小寫英數與單一連字號；不寫 ID 選擇器，不用 `!important`（僅 BASE 的減少動態區例外）。
- 狀態優先用屬性表達：導覽作用中用 `aria-current="page"`，分段選取用 `:has(input:checked)`；對應的 `--active`、`--selected` 修飾保留給不便加屬性的情境。

## 3. 只用權杖（tokens-only）規則與理由

**規則**

1. 顏色（hex、rgb、hsl）、字級、行高、字距、間距、圓角、線寬、陰影與動態時間，只能以字面值出現在 `ems-tokens.css`。
2. `ems-app.css` 一律 `var(--ems-*)`：不得出現色碼、`rgb()`／`hsl()`、px 字級、px 長度、`s`／`ms` 時間。
3. 每個色碼全檔只定義一次（00 色盤）。其他類別在同一類別內不重複；跨類別的相同數值（例如 12px 的字級與 12px 的間距）各自獨立，避免改一個牽動另一個。
4. 每個權杖同一行附註「用在哪裡」。

**為什麼**

- **單一來源**：換品牌色、調字級只改一行，畫布、網頁、報表 PDF 一起更新。
- **可稽核**：所有數值集中列冊，對比度與色盲安全檢查只需驗算一個檔案（紀錄見 `PLAN.md` 與 `_tools/`）。
- **防止漂移**：元件不能自帶近似色（例如第二個「差不多的金色」），檢查腳本會直接擋下。
- **設計與程式對齊**：權杖名稱就是設計語彙，設計師、前端與 AI 協作時講同一套詞。

**不列入權杖的數值**：畫面上的幾何資料，例如絕對定位座標、SVG 路徑與圖表尺寸（694×180 等）、表格欄寬、線稿插畫。這些是「資料」不是「樣式」，由元件或圖表程式計算。

## 4. 權杖區段

| 區段 | 內容 | 重點 |
|---|---|---|
| 00 PALETTE | 40 個色碼（畫面實際使用 39 個，另有淺底用官方深色字標 `--ems-logo-dark`） | synaiq-web 色盤＋◆ 推導色；透明陰影色也在此 |
| 01 SEMANTIC ROLES | 背景、表面、文字、框線、主色、狀態、P2 | 元件優先用這一層 |
| 02 TYPOGRAPHY | 字族堆疊（含 CJK 後備）、字重、字級、行高、字距、數字字形 | 字級以 14 × 1.333 為骨架：19／25／33／44／59 |
| 03 SPACING | 1–28px 共 18 階（畫面實際用到的 gap／padding） | 新元件優先用 4、8、12、16、20、24 |
| 04 RADII / BORDERS / SHADOWS | 圓角 10 階、框線 3 種、紙條傾斜、陰影與外環、焦點框 | 陰影以 var() 組合色盤與框線寬 |
| 05 MOTION | 240ms／0.3s／0.45s、reveal easing、減少動態開關 | 畫布不含動畫；供正式 App 使用 |
| 06 CHARTS | 類別序列、格線、門檻、線寬、虛線、透明度、長條與標記 | 序列順序固定：太陽能 → 電網 → 儲能 |
| 07 LAYOUT | 頁首 74、側欄 208、外距 24、卡片內距 20、控制項高、膠囊、圖示、列高 | 1440 桌面基準 |

## 5. 畫面色彩對照（色碼 → 權杖）

畫面代號：總＝能源總覽、監＝即時監控、需＝需量管理、儲＝儲能管理、警＝警報中心、設＝設備分析、報＝報表中心。「全部」表示七張都有使用。

| 色碼 | 權杖 | 用途 | 使用畫面 |
|---|---|---|---|
| #292a2e | `--ems-chrome-header` | 頁首底、未讀點外環 | 全部 |
| #1d1e20 | `--ems-chrome-sidebar` | 側欄底 | 全部 |
| #2d3229 | `--ems-chrome-active` ◆ | 作用中導覽底帶 | 全部 |
| #5a503b | `--ems-chrome-hairline` ◆ | 頁首細分隔線 | 全部 |
| #45474c | `--ems-chrome-line` ◆ | 場域切換鈕外框 | 全部 |
| #c4c4be | `--ems-inverse` | 深底導覽文字、圖示 | 全部 |
| #f4f4f2 | `--ems-paper` | 頁面底、深底主要字 | 全部 |
| #f8f8f7 | `--ems-paper-light` | 卡片、提示框、標記外環 | 全部 |
| #f2f0e8 | `--ems-paper-warm` | 內嵌面板、紙條、選取列 | 全部 |
| #e8e5da | `--ems-paper-warm-edge` | 流程節點與內嵌面板外框 | 總 |
| #282825 | `--ems-ink` | 主要文字、主按鈕 | 全部 |
| #64645e | `--ems-muted` | 次要文字、刻度 | 全部 |
| #34383a | `--ems-slate` | 儲能序列、頭像、PCS 條 | 全部 |
| #b4b4ac | `--ems-rule` | 基線、輸入與膠囊外框、草圖 | 總 監 需 儲 設 報 |
| #d5d5ce | `--ems-film` | 卡片外框、分隔線 | 全部 |
| #e9e9e3 | `--ems-table-head` | 表頭、格線、分段軌道 | 全部 |
| #afafa0 | `--ems-slip-border` | 示意資料紙條外框 | 全部 |
| #647956 | `--ems-olive` | 工作主色、太陽能序列 | 全部 |
| #576a4a | `--ems-olive-ink` ◆ | 橄欖綠文字、連結 | 全部 |
| #a9bc99 | `--ems-olive-light` | confirmed 區段 | 設 |
| #e1e7dc | `--ems-sage` | 圖示圓底、量表軌道 | 總 儲 設 報 |
| #e5ebdc | `--ems-lit` | 正常色底、ACKED | 總 監 需 儲 警 設 |
| #345e40 | `--ems-kpi-green` | 強調數字、懸停長條 | 全部 |
| #426d4b | `--ems-good` | 狀態正常 | 全部 |
| #cca858 | `--ems-gold` | 字標、金條、電網序列、標註底 | 全部 |
| #9b7b31 | `--ems-gold-deep` ◆ | 契約容量虛線、太陽光芒 | 總 需 |
| #f6ead1 | `--ems-p2-tint` ◆ | P2 一般底 | 總 儲 警 |
| #f7f3eb | `--ems-tou-off` ◆ | 離峰 | 需 儲 |
| #f1e5cc | `--ems-tou-mid` ◆ | 半尖峰 | 需 儲 |
| #e5d0a6 | `--ems-tou-peak` ◆ | 尖峰 | 需 儲 |
| #a5762e | `--ems-warn` ◆ | 警告標記 | 總 需 儲 警 設 |
| #8a5f21 | `--ems-warn-ink` ◆ | 警告文字 | 總 需 警 設 報 |
| #f6ecd7 | `--ems-warn-tint` ◆ | 警告色底 | 總 需 警 設 |
| #a55445 | `--ems-danger` ◆ | 危險標記 | 總 儲 警 設 |
| #96493e | `--ems-danger-ink` ◆ | 危險文字 | 儲 警 設 |
| #f9e9e5 | `--ems-danger-tint` ◆ | 危險色底 | 儲 警 |
| #dedfd477 | `--ems-shadow-paper` | 紙條位移陰影 | 全部 |
| #28282519 | `--ems-shadow-ink-soft` | 分段選取陰影 | 監 |
| #0002 | `--ems-shadow-black-soft` | 提示框陰影 | 總 監 需 報 |
| #352f2d | `--ems-logo-dark` | 淺底官方字標（畫面未使用） | — |

◆ 為推導色：警告、危險只移動色相，保留橄欖綠的明度與金色的彩度，因此與品牌同一家族。所有文字色都已驗算對比度。

## 6. 畫面字體對照（字級 → 權杖）

| 數值 | 權杖 | 用途 | 使用畫面 |
|---|---|---|---|
| 11px | `--ems-font-size-2xs` | 狀態、生命週期、報表類型膠囊 | 警 報 |
| 12px | `--ems-font-size-xs` | 眉標、說明、刻度、圖例、表頭 | 全部 |
| 13px | `--ems-font-size-sm` | 小按鈕、表格內容、頁眉英文標籤 | 全部 |
| 14px | `--ems-font-size-md` | 內文、頁首控制項 | 全部 |
| 15px | `--ems-font-size-ui` | 導覽、KPI 單位 | 全部 |
| 16px | `--ems-font-size-unit-md` | PCS 功率單位 | 儲 |
| 17px | `--ems-font-size-unit-lg` | 電費 NT$ 前綴 | 需 |
| 19px | `--ems-font-size-lg` | 卡片標題（模組 1） | 全部 |
| 20px | `--ems-font-size-unit-xl` | 即時讀值單位 | 監 |
| 22px | `--ems-font-size-figure-2xs` | 提示框數值、SOC 百分號 | 總 需 儲 |
| 24px | `--ems-font-size-brand` | 頁首系統名稱 | 全部 |
| 25px | `--ems-font-size-figure-xs` | 次要數字（模組 2） | 需 儲 報 |
| 26px | `--ems-font-size-figure-donut` | 甜甜圈中心 | 總 |
| 30px | `--ems-font-size-figure-flow` | 能源流節點 | 總 |
| 33px | `--ems-font-size-h1` | 頁標題、統計數字（模組 3） | 監 需 儲 警 設 報 |
| 34px | `--ems-font-size-figure-load` | 廠區負載 | 總 |
| 36px | `--ems-font-size-figure-md` | 需量卡數字 | 總 |
| 40px | `--ems-font-size-figure-lg` | KPI 列 | 總 需 |
| 44px | `--ems-font-size-figure-xl` | PCS 功率、電費合計（模組 4） | 需 儲 |
| 52px | `--ems-font-size-figure-2xl` | 即時有效功率 | 監 |
| 59px | `--ems-font-size-hero` | SOC（模組 5） | 儲 |

| 類別 | 值 → 權杖 |
|---|---|
| 字族 | Manrope＋Noto Sans TC → `--ems-font-body`；Newsreader＋Noto Serif TC＋Songti TC → `--ems-font-display`（頁首系統名稱）；Newsreader＋Noto Serif TC → `--ems-font-heading`；Newsreader → `--ems-font-figure`；Noto Serif TC → `--ems-font-cjk-serif`（標語） |
| 字重 | 300 → `--ems-weight-light`；400 → `--ems-weight-regular`；500 → `--ems-weight-medium` |
| 行高 | 1 → `none`；1.1 → `tight`；1.25 → `snug`；1.35 → `heading`；1.5 → `ui`；1.6 → `body`；1.75 → `prose`（App 長文） |
| 字距 | −0.055em `figure`；−0.04em `figure-sm`；−0.03em `tooltip`；−0.02em `heading`；0.02em `title`；0.04em `nav`；0.06em `label`；0.08em `eyebrow`；0.12em `brand`；0.3em `tagline`（前綴皆為 `--ems-tracking-`） |
| 數字 | 大數字 `--ems-numeric-figure`（lining-nums）；表格與刻度 `--ems-numeric-table`（tabular-nums） |

## 7. 畫面 → 區塊對照

| 畫面 | 主要區塊與元件 |
|---|---|
| 能源總覽 | SHELL（`.ems-header`、`.ems-sidebar`、`.ems-nav-item`）· CARDS（`.ems-card`、`.ems-panel`、`.ems-flow__node`、`.ems-sketch`）· KPI（`.ems-kpi-strip`、`.ems-kpi__value--flow`）· CHARTS（`.ems-chart__line`、`__threshold`、`__callout`、`__label`、`__tooltip`、`.ems-flow__line`、`.ems-donut`、`.ems-meter`）· STATUS（`.ems-status-card`、`--warn`、`.ems-level`）· CONTROLS（`.ems-link-button`、`.ems-pill`） |
| 即時監控 | CONTROLS（`.ems-select`、`.ems-segmented`、`.ems-chip`＋`__check`、`.ems-button`）· CHARTS（`__line--dense`、`__line--spark`、`__reference--nominal`、`__crosshair`、`__tooltip`）· TABLES（`.ems-kv`、`.ems-table__row--compact`、`--selected`）· STATUS（`.ems-live`、`.ems-comm--good`） |
| 需量管理 | KPI · CHARTS（`__bar`、`__bar--live`、`__bar--hover`、`__threshold`、`__reference`、`.ems-tou-ribbon`、`--thin`、`--today`）· STATUS · TABLES（`.ems-kv__row--stacked`）· CONTROLS（`.ems-pill--placeholder`） |
| 儲能管理 | CHARTS（`.ems-soc-ring__*`、`.ems-series--charge/--discharge`、`__bar--current`、`__bar--plan`、`__line--plan`）· STATUS（`.ems-mode--*`、`.ems-state-node`）· KPI（`--hero`、`--xs`）· TABLES（`.ems-kv`） |
| 警報中心 | KPI（`--h1`）· CONTROLS（`.ems-segmented__option--sm`、`.ems-button`、`--outline`）· TABLES（`__row--alarm`、`__row--history`）· STATUS（`.ems-level--p0/p1/p2/info`、`.ems-state--*`、`.ems-stepper`） |
| 設備分析 | KPI · CONTROLS（`.ems-chip`、`.ems-search`、`.ems-button--icon`）· TABLES · STATUS（`.ems-lifecycle--*`、`.ems-comm--*`）· CHARTS（`.ems-stack-bar`、`.ems-meter--xs`） |
| 報表中心 | CONTROLS（`.ems-segmented__option--md`、`.ems-select`、`.ems-button--quiet`、`.ems-pill--xs`）· KPI（`--xs`、`--highlight`）· CHARTS（`.ems-series--grid/pv/bess`、`.ems-legend`）· TABLES（稽核紀錄） |

## 8. 減少動態與對比度要求

**減少動態**

- 所有時間都在 05 區段。系統設定「減少動態」（`prefers-reduced-motion: reduce`）或根元素設 `data-ems-motion="off"` 時，三個時間權杖都會歸零。
- BASE 另對所有元素強制 `animation-duration`／`transition-duration` 為 `--ems-duration-off`。
- 不得在元件內寫死時間；需要新時長時，先在 05 區段新增權杖。

**對比度（WCAG 2.2）**

- 文字對背景至少 4.5:1；24px 以上大字至少 3:1。圖表標記與控制項外框至少 3:1。
- 金色 `--ems-gold`（在卡片上 2.12:1）只用於條、標記、字標與標註底，**不作淺底文字**。標註一律金底墨字（6.55:1）。
- 橄欖綠文字用 `--ems-olive-ink`（5.54:1），不用 `--ems-olive`（4.48:1，只作標記）。
- 狀態一律「圖示＋文字」，不只靠顏色。警告文字用 `--ems-warn-ink`，警告標記用 `--ems-warn`。
- 圖表類別色順序固定：太陽能 → 電網 → 儲能。色盲模擬（protan）最小 ΔE 18.0，一般視覺最小 ΔE 21.4，皆通過。電網金色必附圖例與直接標籤。
- 焦點框：2px `currentColor`，外距 5px（synaiq 規格），不得移除。

## 9. 如何新增元件

1. **先找現成權杖**：在 `ems-tokens.css` 搜尋需要的值（顏色先找 01 語意角色）。
2. **確實需要新數值時**，加進正確的區段：一行一個，同一行註明用途。新顏色要先驗算對比度，類別色另外要跑色盲檢查。
3. **寫規則**：放進對應的 BEGIN／END 區塊，命名 `.ems-<block>__<element>--<modifier>`，所有值都用 `var(--ems-*)`。
4. **執行檢查**：在 `css/` 目錄下 `node css-lint.mjs > check-css.txt 2>&1`，結束碼 0 才算通過。
5. **更新本文件**：第 5–7 節的對照表同步補上。
6. **同步畫布**：若畫布需要同一元件，以相同字面值更新畫面，或回頭調整權杖，保持 1:1。

## 10. React 前端（B\frontend，Tailwind v4）如何共用權杖

前端（React 19＋Tailwind v4＋shadcn 風格元件＋ECharts）直接載入同一份 `ems-tokens.css`，再用 `@theme` 把權杖轉成 Tailwind utilities。這樣 utilities、元件與圖表共用同一來源。

```css
/* B\frontend\src\styles\app.css */
@import "tailwindcss";
@import "../../../css/ems-tokens.css";   /* 依實際相對路徑調整 */

@theme inline {
  /* 顏色 → bg-ems-*、text-ems-*、border-ems-* */
  --color-ems-paper: var(--ems-paper);
  --color-ems-paper-light: var(--ems-paper-light);
  --color-ems-paper-warm: var(--ems-paper-warm);
  --color-ems-ink: var(--ems-ink);
  --color-ems-muted: var(--ems-muted);
  --color-ems-film: var(--ems-film);
  --color-ems-olive: var(--ems-olive);
  --color-ems-olive-ink: var(--ems-olive-ink);
  --color-ems-gold: var(--ems-gold);
  --color-ems-gold-deep: var(--ems-gold-deep);
  --color-ems-good: var(--ems-good);
  --color-ems-warn: var(--ems-warn);
  --color-ems-warn-ink: var(--ems-warn-ink);
  --color-ems-danger: var(--ems-danger);
  --color-ems-danger-ink: var(--ems-danger-ink);
  /* 字族 → font-ems-* */
  --font-ems-body: var(--ems-font-body);
  --font-ems-heading: var(--ems-font-heading);
  --font-ems-figure: var(--ems-font-figure);
  /* 字級 → text-ems-* */
  --text-ems-xs: var(--ems-font-size-xs);
  --text-ems-sm: var(--ems-font-size-sm);
  --text-ems-md: var(--ems-font-size-md);
  --text-ems-lg: var(--ems-font-size-lg);
  --text-ems-h1: var(--ems-font-size-h1);
  --text-ems-figure: var(--ems-font-size-figure-lg);
  /* 圓角 → rounded-ems-* */
  --radius-ems-card: var(--ems-radius-card);
  --radius-ems-button: var(--ems-radius-button);
  --radius-ems-input: var(--ems-radius-input);
  /* 動態 → duration-ems-*、ease-ems-* */
  --ease-ems-reveal: var(--ems-ease-reveal);
}
```

- `@theme` 的語法依需求而定。權杖值是 `var()` 時，建議用 `@theme inline`，讓 utility 直接展開成 `var(--ems-*)`，同時保留減少動態等執行期切換。
- 用法範例：`bg-ems-paper-light border border-ems-film rounded-ems-card`、`font-ems-heading text-ems-h1`。
- **shadcn／Radix**：把元件變數接到權杖，不另訂顏色。

```css
:root {
  --background: var(--ems-paper);
  --foreground: var(--ems-ink);
  --card: var(--ems-paper-light);
  --primary: var(--ems-ink);
  --primary-foreground: var(--ems-paper);
  --muted-foreground: var(--ems-muted);
  --border: var(--ems-film);
  --input: var(--ems-rule);
  --ring: var(--ems-ink);
  --destructive: var(--ems-danger);
}
```

- **ECharts**：圖表配色在執行期讀權杖，不在 JS 寫色碼。

```ts
const css = getComputedStyle(document.documentElement);
const token = (name: string) => css.getPropertyValue(name).trim();
const series = [token('--ems-series-pv'), token('--ems-series-grid'), token('--ems-series-bess')];
```

- 需要沿用畫布元件時，也可直接套用 `ems-app.css` 的 class（例如 `className="ems-card"`），與 utilities 並存。

## 11. 檢查指令

```
cd css
node css-lint.mjs > check-css.txt 2>&1
```

結束碼：0＝通過，1＝有錯。檢查項目：

- **ems-app.css**：色碼、rgb()／hsl()、px 字級、s／ms 時間（依規格）；另檢查 px 長度、未定義的 `var()`、BEGIN／END 區塊順序與成對、class 命名。
- **ems-tokens.css**：00–07 區段齊全、每行附註解、色碼只在 00 且不重複、同類別無重複字面值。
- **涵蓋率**：七張畫面用到的每個色碼都已定義（缺的會逐一列出）。字級、字重、字距、行高、圓角、間距、線寬、虛線、透明度、字族也都要能對到權杖。

輸出全為 ASCII，中文會轉成 `\uXXXX`，避免終端機編碼問題。
