# 徐毅 · 基准库交付

用于保存真实数据来源筛选、原始数据复现、抽样手算、字段探查和最终入库建议。

徐毅当前按 [徐毅-数据补强作业单-v1.md](徐毅-数据补强作业单-v1.md) 执行；该作业单是数据补强的唯一操作口径。

当前应补文件：

- `外部数据源筛选-v1.md`
- `外部数据探查-v1.md`
- `外部数据入库建议-v1.md`
- `数据质量与可追溯补充-v1.md`

外部候选源的具体链接和“补充基准/独立参考/不采用”判定规则均在作业单中，不能自行扩大数据源范围。

## 已下载原始文件（raw_external/，2026-09-13）

Criteo 官方源海外限速（约 30 KB/s），已改用国内镜像下载：

| 文件 | 大小 | 来源镜像 | SHA-256（前 8 位） |
|---|---|---|---|
| `raw_external/criteo_attribution_dataset.tsv.gz` | 622.76 MB | hf-mirror | `94AC7A46` |
| `raw_external/Criteo_Display_Advertising_Challenge.tar.gz` | 4365.5 MB | ModelScope | `8BECCF45` |
| `raw_external/criteo-research-uplift-v2.1.csv.gz` | 297 MB | hf-mirror | `2716E1BF` |

外部数据仅作方法论参考，不并入 KB-01/02/03。命令与哈希见 `数据质量与可追溯补充-v1.md` 第八节。

当前主库仍以 `06-试搭物料/KB-基准库-01～03` 为准；外部数据未经来源、许可、字段、口径四项验收不得覆盖主库。
