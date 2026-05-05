# Cloudflare + Grafana Demo 對外公開操作指南

> 建立日期：2026-04-28  
> 適用情境：EMS Grafana dashboard 對外 demo，資料皆為 Mock data  
> 預設網域：`synaiq-ai.com`  
> 預設公開網址：`https://ems-demo.synaiq-ai.com`  
> 目標讀者：第一次操作 Cloudflare Access / Cloudflare Tunnel 的人

---

## 0. 先講結論

這份文件要完成一件事：

```text
外部訪客打開 https://ems-demo.synaiq-ai.com
        ↓
Cloudflare 要求訪客輸入 email，通過 One-time PIN 驗證
        ↓
Cloudflare Tunnel 把流量送到內網 Grafana
        ↓
訪客只能看 EMS Grafana demo dashboard
```

這次只公開「Grafana 讀取畫面」。不要公開下列服務：

| 不公開項目 | Port | 原因 |
|------------|------|------|
| PostgREST API | `3001` | API 沒有額外身份驗證，公開後任何人可查資料 |
| MCP server | `8765` | MCP 是控制入口，不適合公開給 demo 訪客 |
| MQTT | `1883` | 訊息匯流排，不應暴露到 Internet |
| TimescaleDB | `5432` | 資料庫不能直接公開 |
| Modbus simulator | `5020`, `5021` | 工控協定不應公開 |

推薦方案：

```text
Cloudflare Access + One-time PIN + Cloudflare Tunnel + Grafana Viewer-only demo
```

因為資料是 Mock，所以可以接受「demo 期間較簡化」；但入口仍然要有 Cloudflare Access，不要把 Grafana 裸露在 Internet。

### 0.1 這次不要先動 GW-HOST Nginx

你現有的 EDGE-GATEWAY / GW-HOST Nginx 是正式入口架構，牽涉：

- `synaiq-ai.com` 既有 80 / 443。
- Let's Encrypt / Certbot。
- Nginx 路由到數位人前後端。
- TURN-SVC / WebRTC。
- iptables 防火牆。

這些都不適合為了短期 EMS demo 直接修改。短期 demo 採用 Cloudflare Tunnel 的原因是：

```text
不改 GW-HOST Nginx
不改現有 synaiq-ai.com 主站路由
不開新的 inbound port
只新增 ems-demo.synaiq-ai.com 這個 demo 子網域
```

### 0.2 cloudflared 到底要放在哪裡

`cloudflared` 不是放在 Cloudflare 裡，也不是一定要放在數位人專案主機。它是一個你自己執行的小程式，位置只有一個判斷標準：

```text
那台機器能不能連到 EMS Grafana？
```

如果這台機器執行以下指令會成功，它就可以跑 `cloudflared`：

```bash
curl -I http://localhost:3000/login
```

或，如果它是透過 Tailscale 連 EMS：

```bash
curl -I http://<EMS_TAILSCALE_IP>:3000/login
```

成功時應看到類似：

```text
HTTP/1.1 200 OK
```

最簡單的選擇通常是：

| cloudflared 位置 | Public Hostname 的 Service URL 要填什麼 | 備註 |
|------------------|------------------------------------------|------|
| EMS 所在主機 / WSL Ubuntu | `http://localhost:3000` | 最直覺，因為 Grafana 就在同一台 |
| Windows 主機，但 Grafana port 已映射到 Windows localhost | `http://localhost:3000` | 先用 PowerShell 測 `curl.exe -I http://localhost:3000/login` |
| 另一台能透過 Tailscale 連 EMS 的機器 | `http://<EMS_TAILSCALE_IP>:3000` | 不是一定要數位人主機，只要能連到 EMS |
| GW-HOST Gateway 主機 | `http://<EMS_TAILSCALE_IP>:3000` | 可行，但這次暫不把 Nginx 納入 |

重點：Cloudflare Tunnel 的 `Service URL` 是從 `cloudflared` 所在機器的角度看的。  
如果 `cloudflared` 跑在 EMS 主機上，`localhost` 就是 EMS 主機。  
如果 `cloudflared` 跑在別台機器上，`localhost` 就是那台別的機器，不是 EMS。

### 0.3 你目前已確認的架構與最短選擇

你目前的實際狀態：

```text
GW-HOST：正式對外 IP / gateway / Nginx / TURN-SVC / DNS-FILTER
EMS：Grafana 實際運行主機，位於 EMS-HOST / WSL Ubuntu
GW-HOST ↔ EMS：兩台用 Tailscale 串接
```

你已在 EMS 主機執行：

```bash
curl -I http://localhost:3000/login
```

並得到：

```text
HTTP/1.1 200 OK
```

這代表：

```text
EMS 主機本機可以直接連到 Grafana。
```

所以短期 demo 最快方案是：

```text
cloudflared 跑在 EMS 主機
Public Hostname: ems-demo.synaiq-ai.com
Service URL: http://localhost:3000
```

這條路線不需要：

- 改 GW-HOST Nginx。
- 改 GW-HOST 防火牆。
- 使用 GW-HOST 的 public IP。
- 讓 Cloudflare 走 Tailscale 到 EMS。

Cloudflare Tunnel 的流量方向會是：

```text
訪客
  ↓
Cloudflare
  ↓
Cloudflare Tunnel
  ↓
EMS 主機上的 cloudflared
  ↓
http://localhost:3000
  ↓
Grafana
```

GW-HOST 在這個快速 demo 路線中不是必要節點。

如果未來你想讓 demo 更穩定、不要依賴 EMS Windows/WSL 開著，可以改成：

```text
cloudflared 跑在 GW-HOST
Service URL: http://<EMS_TAILSCALE_IP>:3000
```

但那是第二階段。做之前要先在 GW-HOST 上驗證：

```bash
curl -I http://<EMS_TAILSCALE_IP>:3000/login
```

這次先不走 GW-HOST，避免影響現有 EDGE-GATEWAY。

### 0.4 最短測試：先用 trycloudflare.com 確認 tunnel 概念

這一步不綁 `synaiq-ai.com`，只用 Cloudflare 給的臨時網址測試。適合第一次理解 `cloudflared`。

在能連到 Grafana 的機器上執行：

```bash
cloudflared tunnel --url http://localhost:3000
```

如果這台機器不是 EMS，而是透過 Tailscale 連 EMS，改成：

```bash
cloudflared tunnel --url http://<EMS_TAILSCALE_IP>:3000
```

成功後終端機會印出一個類似這樣的網址：

```text
https://something-random.trycloudflare.com
```

用瀏覽器打開這個網址，應該會看到 Grafana。

這個方式的用途：

- 快速確認 `cloudflared` 能把外部流量帶到 Grafana。
- 不需要 DNS。
- 不需要先設定 Access。

限制：

- 網址是臨時的。
- 不適合正式 demo。
- 沒有使用你的 `ems-demo.synaiq-ai.com`。
- 終端機關掉，tunnel 就會斷。

如果這一步失敗，不要繼續做正式 tunnel，先修本機到 Grafana 的連線。

### 0.5 正式 demo：使用 Cloudflare Dashboard 建 Named Tunnel

正式 demo 不使用 `trycloudflare.com`，而是建立 Named Tunnel：

```text
ems-demo-grafana
```

並綁定：

```text
https://ems-demo.synaiq-ai.com → http://localhost:3000
```

或：

```text
https://ems-demo.synaiq-ai.com → http://<EMS_TAILSCALE_IP>:3000
```

取決於 `cloudflared` 跑在哪台機器。

### 0.6 在 Cloudflare Dashboard 建 Tunnel 的完整填法

1. 打開：

   ```text
   https://dash.cloudflare.com
   ```

2. 進入 `Zero Trust`。
3. 左側找到：

   ```text
   Networks → Tunnels
   ```

   如果畫面名稱略有不同，找 `Tunnels` 或 `Cloudflare Tunnel`。

4. 點 `Create a tunnel`。
5. Connector type 選：

   ```text
   Cloudflared
   ```

6. Tunnel name 填：

   ```text
   ems-demo-grafana
   ```

7. 點下一步，Cloudflare 會要你安裝 connector。

### 0.7 安裝 cloudflared connector：建議用 Linux service，不建議新手先用 Docker

Cloudflare 會在畫面上產生一段安裝指令，裡面包含 tunnel token。請直接複製 Cloudflare 畫面上的指令，不要自己手打 token。

#### Ubuntu / Debian / WSL Ubuntu

在你決定放 `cloudflared` 的 Ubuntu / WSL Ubuntu 上執行。

先安裝 `cloudflared`：

```bash
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
cloudflared --version
```

再執行 Cloudflare 畫面提供的 service install 指令，形式類似：

```bash
sudo cloudflared service install <Cloudflare 畫面給你的 TOKEN>
```

啟動後檢查：

```bash
sudo systemctl status cloudflared --no-pager
```

如果是 WSL Ubuntu，`systemctl` 可能不能用。這時可以先用前景方式測試：

```bash
cloudflared tunnel run --token <Cloudflare 畫面給你的 TOKEN>
```

只要這個視窗開著，tunnel 就會持續運作；視窗關掉，tunnel 就會斷。demo 前請確認電腦不會睡眠。

#### Windows

如果你要把 `cloudflared` 跑在 Windows 主機：

1. 下載 Windows 版 `cloudflared.exe`。
2. 用系統管理員開 PowerShell。
3. 先測 Grafana：

   ```powershell
   curl.exe -I http://localhost:3000/login
   ```

4. 成功後執行 Cloudflare 畫面給的 Windows service install 指令，形式類似：

   ```powershell
   .\cloudflared.exe service install <Cloudflare 畫面給你的 TOKEN>
   ```

5. 檢查服務：

   ```powershell
   Get-Service cloudflared
   ```

#### 為什麼不建議新手先用 Docker 跑 cloudflared

Docker 版 `cloudflared` 常見指令長這樣：

```bash
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <TOKEN>
```

但新手容易踩一個坑：

```text
cloudflared container 裡的 localhost，不是 EMS 主機的 localhost。
```

也就是說，如果你在 Cloudflare Public Hostname 填：

```text
http://localhost:3000
```

但 `cloudflared` 是 Docker container，這個 `localhost` 會指向 `cloudflared` 自己的容器，不是 Grafana。除非你很清楚 Docker network，要把 `cloudflared` 加到 EMS compose network，或使用 host network，否則先不要用 Docker 路線。

### 0.8 確認 Connector 變 Healthy

回到 Cloudflare Tunnel 畫面，等 10-30 秒。

你應該看到 connector 狀態：

```text
Healthy
```

如果不是 Healthy：

1. `cloudflared` 程式沒有跑起來。
2. token 貼錯或過期。
3. 主機不能連 Internet。
4. 公司或機房防火牆擋 outbound HTTPS / QUIC。
5. WSL / Windows 服務被關掉。

先讓 connector Healthy，再設定 Public Hostname。

### 0.9 設定 Public Hostname：這裡最容易填錯

進入 tunnel：

```text
Zero Trust → Networks → Tunnels → ems-demo-grafana → Public Hostnames
```

點 `Add a public hostname`。

填法：

| 欄位 | 填入 |
|------|------|
| Subdomain | `ems-demo` |
| Domain | `synaiq-ai.com` |
| Path | 留空 |
| Type | `HTTP` |
| URL | 看 `cloudflared` 跑在哪裡 |

URL 的選法：

| cloudflared 跑在哪裡 | URL 填什麼 |
|----------------------|-------------|
| EMS 主機 / EMS WSL Ubuntu | `http://localhost:3000` |
| Windows 主機，且 Windows 可開 Grafana | `http://localhost:3000` |
| 另一台 Tailscale 橋接機 | `http://<EMS_TAILSCALE_IP>:3000` |
| GW-HOST Gateway 主機 | `http://<EMS_TAILSCALE_IP>:3000` |

不要填：

```text
https://ems-demo.synaiq-ai.com
```

那是外部入口，不是內部服務地址。

也不要填：

```text
http://localhost:3000
```

除非 `cloudflared` 跟 Grafana 是同一台機器，或該機器自己的 localhost 就能打開 Grafana。

### 0.10 先測 Tunnel，再加 Access

Public Hostname 存好後，先打開：

```text
https://ems-demo.synaiq-ai.com
```

此時如果還沒設定 Access，可能會直接看到 Grafana。

這一步只用來確認 tunnel 能通。確認能通後，立刻進下一步設定 Access，不要長時間裸露。

### 0.11 加 Cloudflare Access 保護

進入 Cloudflare Zero Trust：

```text
Access controls → Applications → Add an application → Self-hosted
```

填：

| 欄位 | 填入 |
|------|------|
| Application name | `EMS Grafana Demo` |
| Subdomain | `ems-demo` |
| Domain | `synaiq-ai.com` |
| Path | 留空 |
| Session duration | `24 hours` 或 demo 期間 |

Policy 填：

| 欄位 | 填入 |
|------|------|
| Policy name | `Allow demo viewers` |
| Action | `Allow` |
| Include selector | `Emails` |
| Emails | 你的 email、demo 觀眾 email |

不要用：

```text
Include Everyone
Action Bypass
```

### 0.12 啟用 One-time PIN

如果 Access login 沒有 One-time PIN，去：

```text
Integrations → Identity providers → Add new identity provider → One-time PIN
```

儲存後，Access policy 裡被允許的 email 就可以收到 Cloudflare 寄出的驗證碼。

### 0.13 最終驗收

用手機 5G 或不在內網的網路測試：

1. 打開：

   ```text
   https://ems-demo.synaiq-ai.com
   ```

2. 應該先看到 Cloudflare Access 登入頁。
3. 輸入允許的 email。
4. 收到 One-time PIN。
5. 輸入 PIN。
6. 進入 Grafana。
7. 能看到 dashboard。
8. 不應能編輯 dashboard 或 datasource。

### 0.14 demo 結束後怎麼關

最快關閉方式：

```text
Cloudflare Zero Trust → Access controls → Applications → EMS Grafana Demo → Disable
```

或：

```text
Zero Trust → Networks → Tunnels → ems-demo-grafana → Public Hostnames → 刪除 ems-demo.synaiq-ai.com
```

也可以在 connector 主機停止 `cloudflared`：

```bash
sudo systemctl stop cloudflared
```

如果是前景執行，直接 Ctrl+C。

---

## 1. 名詞

### 1.1 Domain / Subdomain

你現在有一個 domain：

```text
synaiq-ai.com
```

需要會建立一個 subdomain 給 EMS demo：

```text
ems-demo.synaiq-ai.com
```

使用者看到的是這個網址，不會看到內網 IP、Tailscale IP 或 Docker port。

### 1.2 Grafana

Grafana 是目前 EMS 的儀表板。你本機現在用：

```text
http://localhost:3000/d/ems-overview
```

對外 demo 後，外部訪客會用：

```text
https://ems-demo.synaiq-ai.com
```

### 1.3 Cloudflare Tunnel

Cloudflare Tunnel 是一條「從你的內網主機往 Cloudflare 打出去」的通道。

重點：

- 你不需要開 router port forwarding。
- 你不需要讓 EMS 主機有 public IP。
- 你不需要把 `3000` 直接暴露在 Internet。
- 你需要在一台能連到 Grafana 的機器上跑 `cloudflared`。

Cloudflare 官方說法是：安裝 `cloudflared` 後，它會建立 outbound-only 連線；你再把 public hostname 對應到 local service，例如 `app.example.com → http://localhost:8080`。

### 1.4 cloudflared

`cloudflared` 是 Cloudflare Tunnel 的小程式。它可以跑在 EMS 主機、Windows 主機、WSL Ubuntu、GW-HOST，或任何一台能連到 EMS Grafana 的機器。

判斷方式不是看它是不是數位人專案主機，而是看這台機器能不能成功執行：

```bash
curl -I http://localhost:3000/login
```

或透過 Tailscale：

```bash
curl -I http://<EMS_TAILSCALE_IP>:3000/login
```

Cloudflare Public Hostname 裡的 `Service URL` 是從 `cloudflared` 所在機器的角度看的。這是整個設定最重要的觀念。

### 1.5 Cloudflare Access

Cloudflare Access 是放在網站前面的登入門。

使用者流程：

```text
使用者打開 https://ems-demo.synaiq-ai.com
        ↓
Cloudflare Access 顯示登入頁
        ↓
使用者輸入 email
        ↓
Cloudflare 寄一次性驗證碼 One-time PIN
        ↓
使用者輸入驗證碼
        ↓
Cloudflare 放行到 Grafana
```

### 1.6 One-time PIN

One-time PIN 簡稱 OTP。它讓你不用先串 Google Workspace、Okta 或 Microsoft Entra，也可以用 email 驗證訪客。

demo 最適合用 OTP，因為你只要把訪客 email 加進 Access policy，就能讓他進來。

---

## 2. 本文件採用的 demo 架構

```text
訪客瀏覽器
   │
   │ HTTPS
   ▼
Cloudflare: ems-demo.synaiq-ai.com
   │
   │ Cloudflare Access: One-time PIN 驗證
   ▼
Cloudflare Tunnel
   │
   │ outbound tunnel，不開 inbound port
   ▼
cloudflared 所在主機
   │
   │ Tailscale VPN
   ▼
EMS Grafana
http://<EMS_TAILSCALE_IP>:3000
   │
   ▼
TimescaleDB Mock data
```

### 2.1 為什麼不用直接開 `http://public-ip:3000`

直接開 `3000` 的問題：

- Grafana login 會直接暴露在 Internet。
- 你要處理 router port forwarding / firewall。
- public IP 會變成攻擊面。
- 之後若不小心也開了 `3001`、`8765`、`5432`，風險會變大。

Cloudflare Tunnel 的優點：

- 不需要 inbound port。
- 不需要 public IP。
- 可以用 Cloudflare Access 控制誰能看。
- 可以快速關閉 demo。

---

## 3. 操作前檢查清單

開始前先確認這些事。

### 3.1 Cloudflare 帳戶

你需要：

- 可以登入 Cloudflare dashboard。
- `synaiq-ai.com` 已經在 Cloudflare 帳戶裡。
- 你有權限設定 Zero Trust、Tunnel、DNS、Access。

### 3.2 EMS Grafana 正常

在 EMS 主機上確認：

```bash
cd ~/synaiq/EMS
docker compose ps
```

確認 `ems-grafana` 是 running。

打開本機 Grafana：

```text
http://localhost:3000/d/ems-overview
```

你應該看得到 EMS dashboard。

### 3.3 找出 EMS 的 Tailscale IP

如果 `cloudflared` 跑在 EMS 主機上，可以略過這步，service URL 用：

```text
http://localhost:3000
```

如果 `cloudflared` 跑在另一台 Tailscale 橋接機上，就需要知道 EMS 主機的 Tailscale IP。這台機器不一定是數位人專案主機，只要能連到 EMS Grafana 即可。

在 EMS 主機上執行：

```bash
tailscale ip -4
```

你會看到類似：

```text
100.92.33.44
```

後面文件用這個代表：

```text
<EMS_TAILSCALE_IP>
```

請替換成你的實際值。

### 3.4 在 cloudflared 主機測試能不能連到 Grafana

在你打算安裝 `cloudflared` 的那台機器上測試。

如果 `cloudflared` 跟 Grafana 在同一台機器：

```bash
curl -I http://localhost:3000/login
```

如果 `cloudflared` 在另一台 Tailscale 橋接機：

```bash
curl -I http://<EMS_TAILSCALE_IP>:3000/login
```

成功時會看到類似：

```text
HTTP/1.1 200 OK
```

如果失敗，先不要做 Cloudflare。先修 Tailscale 或網路連線。

---

## 4. Grafana demo 權限設計

這裡有兩種選擇。

### 4.1 推薦給 demo：Cloudflare Access 登入，Grafana 只當 Viewer 顯示

外部訪客只需要過 Cloudflare Access 的 One-time PIN。進到 Grafana 後只能看 dashboard。

優點：

- 訪客流程簡單。
- 不需要幫每個 demo 訪客建立 Grafana 帳號。
- demo 結束後可以直接關掉 Access policy 或 Tunnel。

注意：

- 你仍然要保留 Grafana admin 強密碼。
- 不要公開 Grafana admin 帳號。
- 不要把 Grafana datasource 設成可編輯。

### 4.2 較嚴格：Cloudflare Access + Grafana Viewer 帳號

外部訪客需要兩次登入：

1. Cloudflare Access OTP。
2. Grafana Viewer 帳號。

優點是更安全，缺點是 demo 體驗較麻煩。

### 4.3 本文件建議

因為你目前用途是 demo，資料也都是 Mock，本文件採用：

```text
Cloudflare Access OTP + Grafana Viewer-only demo
```

如果 demo 對象是客戶或公開活動，請至少使用 Cloudflare Access，不要完全裸露 anonymous Grafana。

---

## 5. EMS 專案建議設定

> 這一章是專案設定方向。若你還沒有要改檔，可以先讀懂；真正改檔時再依 project_rules 同步 README / 操作手冊 / 容器速查表。

### 5.1 `.env` 建議新增

`.env` 建議設定：

```env
GRAFANA_PASSWORD=請換成強密碼
GRAFANA_PUBLIC_DOMAIN=ems-demo.synaiq-ai.com
GRAFANA_ROOT_URL=https://ems-demo.synaiq-ai.com/
GRAFANA_ANONYMOUS_ENABLED=true
```

`GRAFANA_PASSWORD` 不要用 `admin`。

### 5.2 `docker-compose.yml` 的 Grafana 建議設定

Grafana service 建議加入：

```yaml
environment:
  GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
  GF_SERVER_DOMAIN: ${GRAFANA_PUBLIC_DOMAIN:-ems-demo.synaiq-ai.com}
  GF_SERVER_ROOT_URL: ${GRAFANA_ROOT_URL:-https://ems-demo.synaiq-ai.com/}
  GF_USERS_ALLOW_SIGN_UP: "false"
  GF_AUTH_ANONYMOUS_ENABLED: ${GRAFANA_ANONYMOUS_ENABLED:-false}
  GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer
```

如果 `cloudflared` 跑在同一台 EMS 主機上，Grafana port 建議只綁 localhost：

```yaml
ports:
  - "127.0.0.1:3000:3000"
```

如果 `cloudflared` 跑在另一台 Tailscale 橋接主機上，這樣綁 localhost 會讓橋接主機連不到 Grafana。此時要改用防火牆或 Tailscale ACL 控制，不要把 `3000` 開到 Internet。

### 5.3 Grafana datasource 要改唯讀

目前 EMS 的 Grafana datasource 若使用 `postgres`，demo 對外前建議改成唯讀帳號。

目標：

```text
Grafana 只能 SELECT，不能寫入、不能改 schema。
```

建議建立：

```sql
CREATE ROLE grafana_reader LOGIN PASSWORD '請換成強密碼';
GRANT USAGE ON SCHEMA api TO grafana_reader;
GRANT SELECT ON api.electricity_measurements TO grafana_reader;
GRANT SELECT ON api.factory_measurements TO grafana_reader;
```

然後把 Grafana datasource 改成：

```yaml
user: grafana_reader
editable: false
```

---

## 6. Cloudflare Zero Trust 第一次設定

### 6.1 進入 Cloudflare dashboard

1. 打開：

   ```text
   https://dash.cloudflare.com
   ```

2. 登入你的 Cloudflare 帳號。
3. 確認左側或首頁能看到 `synaiq-ai.com`。
4. 進入 `Zero Trust`。

如果你是第一次使用 Zero Trust，Cloudflare 可能要求：

- 建立 organization / team name。
- 選擇方案。
- 填一些基本資料。

demo 用途通常 Free plan 即可。畫面名稱可能會隨 Cloudflare 調整，但你要找的是：

```text
Zero Trust
```

---

## 7. 啟用 One-time PIN

如果 Cloudflare Access 還沒有身份提供者，先啟用 One-time PIN。

操作：

1. 進入 Cloudflare Zero Trust dashboard。
2. 找到：

   ```text
   Integrations → Identity providers
   ```

   如果畫面不同，找：

   ```text
   Settings → Authentication → Identity providers
   ```

3. 點 `Add new identity provider`。
4. 選 `One-time PIN`。
5. 儲存。

完成後，Cloudflare 可以寄一次性驗證碼給被允許的 email。

注意：

- 訪客必須被 Access policy 允許，才會真的收到 PIN。
- 被擋的人可能也會看到「已寄出」的畫面，但實際不會收到信，這是 Cloudflare 的安全設計。
- PIN 有效時間有限，過期就重新申請。

---

## 8. 建立 Cloudflare Tunnel

### 8.1 選擇 cloudflared 安裝位置

先決定 `cloudflared` 要跑在哪裡。

| 選項 | Service URL | 建議程度 |
|------|-------------|----------|
| EMS 主機 | `http://localhost:3000` | 最簡單 |
| 另一台 Tailscale 橋接機 | `http://<EMS_TAILSCALE_IP>:3000` | 只要能連到 EMS Grafana 即可 |

如果某台橋接機是常開的，而且已經能透過 Tailscale 連 EMS，可以把 `cloudflared` 放在那台機器。若 EMS 主機本身會在 demo 期間保持開機，放 EMS 主機最簡單。

### 8.2 在 Cloudflare 建 Tunnel

操作：

1. 進入 Cloudflare Zero Trust dashboard。
2. 找到：

   ```text
   Networks → Tunnels
   ```

3. 點 `Create a tunnel`。
4. 選 `Cloudflared`。
5. Tunnel 名稱填：

   ```text
   ems-demo-grafana
   ```

6. Cloudflare 會顯示安裝 `cloudflared` 的指令。
7. 選擇你的主機作業系統，例如 Linux / Docker / Windows。
8. 到那台主機上執行 Cloudflare 給你的指令。

重要：

- Cloudflare 給的指令裡會有 token。
- token 等同這條 tunnel 的憑證，不要貼到公開文件或聊天。
- 如果 token 外洩，請到 Cloudflare 重新 rotate / delete tunnel。

### 8.3 確認 Connector 變成 Healthy

在 Cloudflare Tunnel 畫面，你應該看到 connector 狀態變成：

```text
Healthy
```

如果不是 Healthy：

1. 確認 `cloudflared` 程式有在跑。
2. 確認該主機能上網。
3. 確認系統時間正確。
4. 重新執行 Cloudflare 提供的 install / run command。

---

## 9. 加入 Public Hostname

Tunnel 建好後，要告訴 Cloudflare：`ems-demo.synaiq-ai.com` 要轉去哪個內部服務。

操作：

1. 進入：

   ```text
   Zero Trust → Networks → Tunnels
   ```

2. 點進 `ems-demo-grafana`。
3. 找 `Public Hostnames`。
4. 點 `Add a public hostname`。
5. 填入：

   ```text
   Subdomain: ems-demo
   Domain: synaiq-ai.com
   Path: 留空
   Type: HTTP
   URL: http://<EMS_TAILSCALE_IP>:3000
   ```

如果 `cloudflared` 跑在 EMS 主機上，URL 改成：

```text
http://localhost:3000
```

儲存後，Cloudflare 會把 public hostname 對應到 tunnel。若你的 DNS zone 在同一個 Cloudflare 帳戶，Cloudflare 通常會自動建立對應 DNS record。

---

## 10. 建立 Cloudflare Access Application

Tunnel 只是把路打通；Access 才是登入保護。

### 10.1 新增 Self-hosted application

操作：

1. 進入 Cloudflare Zero Trust dashboard。
2. 找到：

   ```text
   Access controls → Applications
   ```

3. 點 `Add an application`。
4. 選 `Self-hosted`。
5. Application name 填：

   ```text
   EMS Grafana Demo
   ```

6. Session Duration 建議填：

   ```text
   24 hours
   ```

   若 demo 會連續多天，可以用 `7 days`。

7. Public hostname 填：

   ```text
   Subdomain: ems-demo
   Domain: synaiq-ai.com
   Path: 留空
   ```

這個 hostname 必須和 Tunnel 的 public hostname 一樣。

### 10.2 建立 Allow policy

Policy 建議：

```text
Policy name: Allow demo viewers
Action: Allow
Session duration: 24 hours 或 7 days
Include: Emails
Value: 允許觀看 demo 的 email
```

例如：

```text
alice@example.com
bob@example.com
```

不要選這些危險設定：

| 不建議設定 | 為什麼 |
|------------|--------|
| Include Everyone | 等於任何人都能進 |
| Include Login Methods = One-time PIN | 等於任何能收 email 的人都可能進 |
| Bypass | 會跳過 Access 保護 |

Cloudflare 官方也提醒，`Everyone` 或只用 `Login Methods: One-time PIN` 這類 Allow policy 可能造成任何人可進入應用。

### 10.3 儲存 application

完成後，Access application 會保護：

```text
https://ems-demo.synaiq-ai.com
```

---

## 11. 第一次外部驗收

請用「不在內網、不連 Tailscale」的設備測試，例如手機 5G。

### 11.1 打開 demo URL

```text
https://ems-demo.synaiq-ai.com
```

你應該先看到 Cloudflare Access 登入頁，而不是直接看到 Grafana。

### 11.2 測試 One-time PIN

1. 輸入被 policy 允許的 email。
2. 點寄送驗證碼。
3. 到信箱收 Cloudflare PIN。
4. 回到登入頁輸入 PIN。
5. 應該進入 Grafana。

### 11.3 確認只能看 dashboard

進入 Grafana 後確認：

- 看得到 EMS dashboard。
- 看得到 KC 溫度、濕度、壓力、設備狀態。
- 不應該能修改 dashboard。
- 不應該能進 datasource 編輯頁。
- 不應該看到 admin 設定入口。

### 11.4 確認其他服務沒有公開

在外部網路測試時，這些不應可用：

```text
https://ems-demo.synaiq-ai.com:3001
https://ems-demo.synaiq-ai.com:8765
https://ems-demo.synaiq-ai.com:1883
```

如果你有其他 public IP，也不要讓下列 port 被 Internet 掃到：

```text
3001, 8765, 1883, 5432, 5020, 5021
```

---

## 12. Demo 前整理 Grafana 畫面

正式 demo 前，建議建立一份專用 dashboard，例如：

```text
EMS Demo Overview
```

保留：

- 電力即時功率。
- 電力趨勢。
- KC 溫度 / 濕度 / 壓力。
- Pump / Valve 狀態。
- 最新工廠資料表。

隱藏或移除：

- 內部 service name。
- debug panel。
- datasource 細節。
- MCP 操作資訊。
- 任何 token、IP、內網 hostname。
- 任何真實客戶資料。

雖然目前都是 Mock data，仍建議讓 demo dashboard 看起來像產品畫面，不要像工程排錯畫面。

---

## 13. Demo 當天操作流程

### 13.1 Demo 前 30 分鐘

1. 確認 EMS 容器正常：

   ```bash
   cd ~/synaiq/EMS
   docker compose ps
   ```

2. 確認 Grafana 本機正常：

   ```text
   http://localhost:3000/d/ems-overview
   ```

3. 在 cloudflared 主機確認能連 Grafana：

   ```bash
   curl -I http://<EMS_TAILSCALE_IP>:3000/login
   ```

4. 在 Cloudflare Tunnel 頁確認 connector 是 Healthy。
5. 用手機 5G 打開：

   ```text
   https://ems-demo.synaiq-ai.com
   ```

6. 用 demo email 跑一次 OTP 登入。

### 13.2 Demo 中

只分享：

```text
https://ems-demo.synaiq-ai.com
```

不要分享：

- Grafana admin 帳密。
- Cloudflare token。
- Tailscale IP。
- PostgREST URL。
- MCP endpoint。

### 13.3 Demo 後

demo 結束後建議做其中一項：

| 方法 | 效果 |
|------|------|
| Disable Access application | 外部網址仍存在，但不能進 |
| Remove allowed email | 特定訪客不能再登入 |
| Delete public hostname route | Cloudflare 不再轉發到 Grafana |
| Stop cloudflared | Tunnel 中斷，外部不可用 |
| 關閉 Grafana anonymous viewer | 即使 tunnel 還在，也需要 Grafana 登入 |

---

## 14. 常見問題排除

### 14.1 打開 `ems-demo.synaiq-ai.com` 顯示 Cloudflare 1016

常見原因：DNS record 指到 tunnel，但 tunnel 沒有正常跑。

處理：

1. 到 Cloudflare `Networks → Tunnels` 看 connector 是否 Healthy。
2. 如果不是 Healthy，回 cloudflared 主機重啟服務。
3. 確認 Public Hostname 還在。

### 14.2 Cloudflare Access 登入後看到 502 / 504

代表 Cloudflare 到 origin 失敗。

處理：

1. 在 cloudflared 主機執行：

   ```bash
   curl -I http://<EMS_TAILSCALE_IP>:3000/login
   ```

2. 如果 curl 失敗，修 Tailscale 或 EMS Grafana。
3. 如果 curl 成功，檢查 Tunnel 的 service URL 是否填錯。

### 14.3 訪客收不到 One-time PIN

可能原因：

- email 沒有加進 Access policy。
- policy 選錯 selector。
- 信件被垃圾信或郵件安全系統擋掉。
- 訪客輸入的 email 和 policy 裡的不完全一致。

處理：

1. 回 Access application 檢查 policy。
2. 確認 Include 使用 `Emails`，不是 `Everyone`。
3. 加入正確 email。
4. 請訪客重新申請 PIN。

### 14.4 任何人都可以進 demo

立刻檢查 Access policy。

危險設定：

```text
Include: Everyone
Include: Login Methods → One-time PIN
Action: Bypass
```

修正：

```text
Action: Allow
Include: Emails
Value: 指定 demo 訪客 email
```

### 14.5 進入 Grafana 後可以編輯 dashboard

代表 Grafana 權限太高。

處理：

1. 確認外部訪客不是用 admin 帳號登入。
2. 確認 anonymous role 是 `Viewer`，不是 `Editor` 或 `Admin`。
3. 確認 datasource `editable: false`。
4. Demo 前不要分享 admin 密碼。

### 14.6 Grafana dashboard 沒資料

處理：

```bash
cd ~/synaiq/EMS
docker compose ps
docker compose logs -f ingest kc-ingest
curl 'http://localhost:3001/electricity_measurements?order=time.desc&limit=1'
curl 'http://localhost:3001/factory_measurements?order=time.desc&limit=1'
```

如果本機 API 都沒資料，問題不是 Cloudflare，是 EMS 資料管線。

---

## 15. 安全邊界

### 15.1 可以公開

| 項目 | 條件 |
|------|------|
| Grafana dashboard | Access 保護，Viewer-only |
| Mock data | 不含真實客戶、真實設備、真實地點 |

### 15.2 不可以公開

| 項目 | 原因 |
|------|------|
| Cloudflare tunnel token | token 外洩可註冊 connector |
| Grafana admin 密碼 | 可修改 dashboard / datasource |
| Tailscale auth key | 可加入 tailnet |
| Postgres 密碼 | 可讀寫資料庫 |
| Telegram bot token | 可發送或濫用 bot |
| MCP endpoint | 控制入口，不是展示入口 |

### 15.3 demo 結束後的最低清理

至少做：

1. 移除 demo 訪客 email。
2. 關閉或刪除 Access application。
3. 關閉 Public Hostname route。
4. 停止 cloudflared。
5. 若曾開 Grafana anonymous viewer，改回 `false`。

---

## 16. 最小執行順序

如果你只想照順序做，不想理解太多，照這份清單：

1. 確認 `http://localhost:3000/d/ems-overview` 可用。
2. 找到 EMS Tailscale IP：`tailscale ip -4`。
3. 在你選定的 `cloudflared` 主機測試：`curl -I http://localhost:3000/login` 或 `curl -I http://<EMS_TAILSCALE_IP>:3000/login`。
4. Cloudflare Zero Trust 啟用 One-time PIN。
5. Cloudflare 建 Tunnel：`ems-demo-grafana`。
6. 在你選定的 `cloudflared` 主機安裝並啟動 `cloudflared`。
7. Tunnel 加 Public Hostname：若 `cloudflared` 與 Grafana 同機，填 `ems-demo.synaiq-ai.com → http://localhost:3000`；若透過 Tailscale 連 EMS，填 `ems-demo.synaiq-ai.com → http://<EMS_TAILSCALE_IP>:3000`。
8. Access controls 加 Self-hosted application：`EMS Grafana Demo`。
9. Access policy 用 `Allow + Emails`，填允許 demo 的 email。
10. 用手機 5G 打開 `https://ems-demo.synaiq-ai.com`。
11. 收 OTP，登入，確認只能看 dashboard。
12. Demo 結束後移除 email 或停用 Access application。

---

## 17. 官方文件參考

- Cloudflare Tunnel overview：<https://developers.cloudflare.com/tunnel/>
- Cloudflare Tunnel routing / Public hostname：<https://developers.cloudflare.com/tunnel/routing/>
- Cloudflare Access self-hosted public application：<https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/>
- Cloudflare Access One-time PIN：<https://developers.cloudflare.com/cloudflare-one/identity/one-time-pin/>
- Cloudflare Access policies：<https://developers.cloudflare.com/cloudflare-one/access-controls/policies/>
- Tailscale subnet routers：<https://tailscale.com/kb/1019/subnets>
