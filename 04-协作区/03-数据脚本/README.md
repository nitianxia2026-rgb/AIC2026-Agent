# 数据与测试脚本说明

> 01–05 是已完成的基准库流水线；当前新增 P2-01 出价仿真时，不改写已有脚本和输出。公开助手自动化测试位于本目录对应子目录。
> **零第三方依赖**：只要电脑上有 python3（macOS 自带），不用装任何库。

## 0. 环境检查（1 分钟）

终端（Terminal）里执行：

```bash
python3 --version    # 显示 3.8 以上就行
```

## 1. 目录约定

```
scripts/
├── explore_data.py / build_benchmark.py / synthesize_curve.py / verify_monotonic.py / make_synthetic_base.py
├── data/raw/          ← 你把下载的 ad_performance.csv 放这里（文件夹没有就手动建）
└── outputs/           ← 所有结果自动生成在这里（不用建）
```

**所有命令都在 scripts 文件夹里执行**（终端先 `cd` 到这个文件夹）。

## 2. 执行顺序（5 条命令）

| 步 | 命令 | 干什么 | 产出 |
|---|---|---|---|
| ① | （手动）下载飞桨数据集放到 data/raw/ | aistudio.baidu.com/datasetdetail/55268，注册百度账号后免费下载 | data/raw/ad_performance.csv |
| ② | `python3 explore_data.py` | 字段/缺失/分组规模/率刻度探查 | outputs/01-探查报告.md |
| ③ | `python3 build_benchmark.py` | 分组统计转化端基准（均值+P25/P50/P75） | outputs/02-基准表-转化端.csv + draft.md |
| ④ | `python3 synthesize_curve.py` | 合成曝光端基准（CTR/CPM/CPC）+ 出价梯度曲线 | outputs/03、04 两个 csv + draft.md |
| ⑤ | `python3 verify_monotonic.py` | 单调性 + 全表 sanity 校验 | outputs/05-校验报告.md，**全 PASS 才算过** |

该流水线已完成并通过校验；需要复现时仍按以上顺序执行。

## 3. 每步你要人工看什么（QC）

- **②之后**：打开 01-探查报告 → 看"三、率刻度判定"和"五、交叉分组规模" → 在"六、人工判断"补 2–3 句 + 勾数据来源。
- **③之后**：从 02 的 CSV 里**随机抽 1 个组**，用 Excel 筛出原始数据手算一个均值，和表对上才算数（防脚本错）。
- **④之后**：打开 draft.md 看"演算示例"（500 元预算那段），数字要能对上你的直觉量级。
- **⑤之后**：校验报告必须**全 PASS**。有 FAIL → 把报告发给队长，**不要手工改数字**。

## 4. 兜底：飞桨下载失败怎么办

1. `python3 make_synthetic_base.py` → 生成 data/raw/ad_performance_synthetic.csv
2. 用文本编辑器打开 explore_data.py 和 build_benchmark.py，把顶部 `INPUT_CSV = "..."` 改成 `data/raw/ad_performance_synthetic.csv`
3. 照常执行 ②→⑤，**并在探查报告人工判断里声明"数据来源=合成"**（答辩口径同步告诉队长）

## 5. 常见问题

- **"未识别到的业务列"不是"无"** → 真实 CSV 列名可能和预期不同：打开 explore_data.py 顶部 `ALIASES`，把真实列名加进对应候选列表（英文/异名都行），重跑。
- **解码失败** → 用 Excel 另存为"CSV UTF-8"再放回 data/raw/。
- **率数字很大（如 5.0）** → 脚本会自动判定百分数刻度并 ÷100，报告第三节有说明，确认一下即可。

## 6. 当前 P2-01 如何交

出价仿真任务看 `../04-交付收集/03-徐毅-数据与算法/徐毅-出价仿真数据与脚本作业单-v1.md`。代码放本目录，06–08 输出放 `outputs/`；交付说明和校验报告登记在徐毅固定交付目录。

## 7. 公开助手自动化测试

浏览器脚本及运行说明位于 `公开助手自动化测试/`。它只采集回答和截图，不自动判定通过；判定结果登记到陈钰涛固定交付目录。

## 8. 出价仿真 API 候选

`bid_api.py` 是 `bid-sim-v1.2` 的零第三方依赖、只读 HTTP 封装，提供：

- `GET /healthz`
- `GET /openapi.json`
- `POST /bid-simulate`

本地验收：

```bash
python3 verify_bid_api.py
```

当前版本：`bid-api-v0.2`＋`bid-sim-v1.2`。本地结果为10/10 PASS，其中包含10次连续一致调用、OpenAPI契约、API Key鉴权、非法JSON、计费冲突、消耗比例缺失、回传状态缺失和回传未就绪拒绝。API不再默认“消耗60%”“审核通过”或“回传就绪”。该结果只证明本地封装可用，不等于已部署或比赛平台可访问。

正式接入硬门：部署为稳定HTTPS；设置`BID_SIM_API_KEY`；从比赛网络完成10次连续成功；在助手中验证正常、缺参和失败降级；保留KB-04兜底。任何一项不通过，都不把API挂入正式助手。

### 8.1 部署包

- `Dockerfile`：只复制API、算法和KB-02合成基准CSV；容器监听`PORT`环境变量。
- `render.yaml`：Render Blueprint示例，需在服务端设置秘密变量`BID_SIM_API_KEY`。
- `.dockerignore`：避免把其他数据和报告打进镜像。

部署完成后导出平台可导入的OpenAPI文件：

```bash
python3 export_bid_openapi.py --server-url https://你的稳定域名
```

生成`bid_simulate.openapi.json`。不得把真实API Key写进Schema、仓库、截图或聊天；Key只填平台的鉴权/请求头配置，Header名为`X-API-Key`。

### 8.2 平台挂载字段（以实际界面为准）

依据2026-09-18平台截图，操作如下：

1. 助手“工具”页选择“创建API工具”。
2. 名称填`投手智囊-出价测试带`。
3. 在“OpenAPI Schema”文本框直接粘贴`bid_simulate.openapi.json`；也可点“从URL导入”，填写`https://你的域名/openapi.json`。
4. “鉴权方式”选择“API Key”。Schema声明的Header名为`X-API-Key`；密钥只填平台鉴权字段，不写入Schema。
5. 确认“可用工具”只出现一行：名称`bid_simulate`、方法`post`、路径`/bid-simulate`。若出现健康检查工具，说明Schema版本错误，不保存。
6. 点击该行“测试”，完成正常请求后再保存。随后挂到助手，并测试缺消耗比例、缺回传状态、计费冲突和服务不可用降级。

### 8.3 为什么当前不做自定义MCP

平台官方MCP说明确认：线上MCP必须使用`sse`或`http/streamable`协议，配置根节点为`mcpServers`，服务端需要支持MCP连接和工具发现；`stdio`仅限本机测试。当前`bid_api.py`是REST/OpenAPI服务，不是MCP Server，不能把URL填进MCP配置冒充接入。API工具已经原生覆盖单一出价仿真能力，额外包装MCP不增加业务链路，只增加传输和运维风险。
