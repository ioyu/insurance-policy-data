# insurance-policy-data

保險條款離線閱讀器（tii）的條款目錄資料。App 從本 repo 的 `main` 分支讀取：

```text
https://raw.githubusercontent.com/ioyu/insurance-policy-data/main/manifest.json
```

PDF 不放在這裡；每份文件的 `source_url` 指向保險公司官方網站。

## 檔案

| 路徑 | 內容 |
|---|---|
| `manifest.json` | `schema_version`、`data_version`、`generated_at`、`files`（每個資料檔的 `path`、`sha256`、`size`） |
| `companies.json` | 保險公司 |
| `products/{company_id}.json` | 該公司的商品 |
| `documents/{company_id}.json` | 該公司的條款文件（每個版本一筆） |

App 只在 `data_version` 比本機新時更新，下載 `files` 列出的每個檔案並比對 `sha256` 與 `size`，全部通過才寫入。

## 修改規則

- id 永不重用、永不改名。
- 新版條款是新的文件 id。舊文件保留，`status` 改為 `superseded` 或 `withdrawn`。
- 不刪除任何列。刪除的列在已安裝的 App 中仍會保留。
- `status` 只能是 `draft`、`active`、`superseded`、`withdrawn`、`unknown`。

## 修改流程

```bash
python3 tools/validate.py
python3 tools/build_manifest.py   # 重算 hash、遞增 data_version
python3 -m pytest -q
git commit -am "data: ..."
```

CI（`.github/workflows/validate.yml`）在 push 與 PR 時執行上述檢查；`build_manifest.py --check` 失敗代表忘了重算 manifest。

JSON 以原始 bytes 存放（`.gitattributes`：`*.json -text`），不可讓 git 轉換換行，否則 hash 不符。
