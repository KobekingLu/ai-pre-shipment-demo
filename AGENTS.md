# AGENTS.md

## Project / 專案名稱
AI Pre-Shipment Risk Decision Agent

## Project Goal / 專案目標
這個專案是公司內部 AI 競賽用的 Demo。

目標是做出一個 **可執行、可展示** 的 AI agent prototype，協助在 ES / sample 出貨前完成 shipment risk review。

這個 agent 希望能協助 PM / AE / DQA / RD：
- 盤點 available data sources
- 選擇 usable evidence
- 比對 expected vs actual
- 檢查 known issues
- 評估 shipment risk
- 提出 next workflow action

---

## Current Stage / 目前階段
目前專案已超過最早期 prototype 階段，已具備：

- real workbook review flow
- fake demo scenario flow
- JSON output
- bilingual HTML overview page
- bilingual HTML detail pages

現階段仍是 **demo prototype**，不是 production system。

優先順序：
1. keep the demo runnable
2. keep the HTML pages demo-friendly
3. keep the project easy to modify
4. gradually move toward real DUT-connected flow

請不要 over-engineer。

---

## Current Working Modes / 目前工作模式
目前這個專案有兩種主要模式：

### 1. Real Workbook Review Mode
用於 `input_data/` 內的真實 Excel workbooks。

Agent 會：
1. inspect workbook files
2. identify sheet roles
3. extract expected / actual / known issue evidence
4. evaluate risk
5. render HTML review result

### 2. Demo Scenario Mode
用於 `demo_cases/` 內的 fake demo cases。

Agent 會：
1. load simplified expected / actual / known issue files
2. normalize them into the same analysis structure
3. evaluate risk
4. render HTML review result

這兩種模式都應盡量共用相同的 analysis structure 與 rendering logic。

---

## Current Output / 目前輸出
目前應維持以下輸出能力：

- JSON analysis outputs
- bilingual HTML overview page
- bilingual HTML detail pages
- support for:
  - Go
  - Conditional Go
  - No-Go

HTML output 應維持 demo-friendly，並幫助解釋：
- what the agent found
- where the risk is
- why the recommendation was made
- who should handle next action

---

## Input Data / 輸入資料
### Current input folders
- `input_data/` → 真實 workbook inputs
- `demo_cases/` → fake demo cases

### Real workbook inputs may include
- tracking sheet
- system information sheet
- known issue sheet
- release note related content

### Demo case inputs may include
- `expected_config.csv`
- `actual_sysinfo.txt`
- `known_issues.csv`

如果真實資料格式不一致，Version 1 可接受：
- partial parsing
- simplified assumptions
- fake data 補齊缺少情境
- manual mapping

---

## HTML Presentation Rules / HTML 呈現原則
目前 HTML 是 demo 核心輸出之一，請遵守：

1. 保持目前 overview + detail page 結構
2. 保持 bilingual style（English + Traditional Chinese）
3. section titles 應維持雙語
4. key summary text 應維持雙語
5. technical details 可主要保留英文
6. 不要讓頁面過度擁擠
7. 維持「像 AI Agent workflow demo」的語氣，而不是只像 static report

建議保留 agent wording：
- agent inspected
- agent selected
- agent compared
- agent detected
- agent found missing evidence
- agent recommended next action

---

## Practical Development Rules / 實作原則
- 使用 Python
- 模組保持小而實用
- 優先 readable code，不要過度抽象
- 註解清楚即可
- 邏輯要容易調整
- Version 1 避免不必要 framework
- 盡量重用既有 parser / decision / rendering flow
- 新功能優先以增量方式加入，不要推翻現有流程

---

## Suggested Files / 建議檔案結構
目前常見檔案包括：

- `AGENTS.md`
- `README.md`
- `NEXT_STEP.md`
- `input_data/`
- `demo_cases/`
- `output/`

以及主要程式檔：
- parser / inspector related code
- decision logic code
- HTML rendering code
- demo entry point

如有需要，可擴充：
- DUT collection helper
- actual execution sheet generator
- field normalization helper

---

## Current Main Goal / 目前主要目標
目前主要目標不再只是「做出最小 runnable prototype」，而是：

### Current main goal
保持現在的 demo 可展示，並逐步升級到：

- PM tracking sheet as expected input
- DUT-collected actual data as actual input
- agent-generated actual execution sheet
- automatic compare + shipment review output

---

## Next Direction / 下一步方向
當需要往下一階段推進時，優先思考：

1. 如何讓 agent 讀 PM tracking sheet
2. 如何從 DUT 收集 actual data
3. 如何生成 `actual_execution_sheet`
4. 如何用同一套 compare / risk logic 輸出 review result
5. 如何保留目前 bilingual HTML demo 優勢

---

## Important Notes / 重要提醒
- 第一優先是 demo 可展示、可錄影
- 不要因為追求完美架構而破壞目前可用的成果
- fake demo cases 不是臨時垃圾資料，而是正式 demo 的一部分
- 真實 workbook flow 與 fake demo flow 都應維持可運作
- 若資料不足，agent 應明確指出 missing evidence，而不是假裝知道答案
- output 要幫助 PM / AE / RD / DQA 理解與處理問題

---

## When Unsure / 不確定時
如果遇到資料格式不明、欄位名稱不一致、資訊不足的情況：

1. 先列出觀察到的結構
2. 提出合理 mapping 建議
3. 用最小假設先讓 demo 可跑
4. 盡量保留既有 output structure
5. 不要輕易破壞目前 bilingual HTML demo 能力