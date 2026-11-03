# Market Voices / 市场观点

A bilingual, evidence-aware publishing toolkit: collect and summarize once,
serve static content to everyone. No reader accounts, model calls or API keys in the site.

这是从 MoneyTalk 人物观点实验拆出的独立工具。网站供读者阅读，AI仅参与维护者的内容生产。
支持本机 Codex Skill 和模型API；两者共用契约、核验、审核与发布流程。
**状态：公开静态站已部署；首次盘后生产试运行已排程，连续运营和读者验证仍待完成。**

在线阅读：https://skeylove.github.io/market-voices/
源码：https://github.com/SkeyLove/market-voices

首次试运行：北京时间2026-11-04 06:00（美东2026-11-03收盘后一小时），GitHub调度目标约15分钟内。
当前初始期刊为明确标注的2025历史访谈精选，不代表本周观点；不虚构六期真实备用稿。

## 1. 无密钥演示（Python 3.12+）

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install .
market-voices --state /tmp/voices-demo demo --output /tmp/voices-site
python -m http.server 8771 --bind 127.0.0.1 --directory /tmp/voices-site
```

打开 http://127.0.0.1:8771/ 。使用新的状态/输出目录，重复构建不会覆盖已有版本。
演示包含30条虚构观点、3类身份、6份虚构备用期刊，均明确标注合成演示；不是市场数据或运营成绩。
安装后完全不调用网络即可构建演示（安装依赖本身需联网）。从项目根路径及子路径访问都支持。

## 2. 配置自己的来源

```bash
market-voices --state ./state register --input examples/sources.json
market-voices --state ./state collect
market-voices --state ./state status
```

示例来源默认未经准入。请先确认身份、独立来源组与摘要链接用途，将自己的来源登记为
`verified=true`、`rights=summary_link_only`或`licensed`，不要将配置开关当成程序已经核实权利。
RSS内容只有完整`content`字段可作为full_text；摘要、标题及缺失日期记录不会直接进入发布。
X使用`ingest`导入原帖正文与日期；YouTube安装`pip install '.[youtube]'`后使用
`video --source <source-id> --url <video-url> --published <aware-ISO-time> --title <title>`。
YouTube频道自动发现和云端字幕可得性不作保证；来源不可得时记录失败，绝不编造补齐。

## 3. 选择整理方式

**Codex Skill，不额外调用模型API：** 把`skills/market-voices`目录安装到自己的
`~/.agents/skills/market-voices`，在Codex调用`$market-voices`并指定状态目录。
使用当前Codex模型额度，非免费无限推理。Skill内含命令、输出契约和停止条件。

**API：** 将`examples/production.json`复制到私有位置，配置自己的模型。
默认本地配置路径是Linux等系统`~/.config/market-voices/model.json`，macOS为
`~/Library/Application Support/market-voices/model.json`；可用`--config`或
`MARKET_VOICES_CONFIG`覆盖。密钥使用`MARKET_VOICES_API_KEY`，或放在自己的0600私有配置文件。

```bash
export MARKET_VOICES_CONFIG=/private/path/model.json
# 在你自己的终端安全设置 MARKET_VOICES_API_KEY；不要写入仓库。
market-voices --state ./state summarize
# 历史档案整理需显式添加 --include-history，定时生产默认仅处理近7天。
```

费率快照默认采用2026-11-03官方Flash峰值、输入缓存未命中价：USD0.30/1M输入、USD1.20/1M输出。
`currency_to_cny=8`是保守预算换算参数，**不是实时汇率**。31日后快照失效并停止付费请求，需复核更新。
固定月度上限30元，默认每日12次尝试；故障重试同样计费。缓存命中按未命中价计入预算，账本为保守估计而非账单。
官方费率：https://api-docs.deepseek.com/quick_start/pricing/ 。供应商价格变化需同步配置并核对真实账单。

调用前按UTF-8字节上界及最大输出预留费用，写入私有持久状态后才调用。
网络结果不明保留预留额；额度不足停止生成。每份输入最多两次自动尝试，修改内容后才产生新的输入指纹。
语义、翻译和人物归属仍需要抽样人工检查；机械校验并不证明模型判断正确。

## 4. 审核、期刊和发布

```bash
market-voices --state ./state candidates --output /private/path/candidates-new.json
# 用Skill或API生成后，以相同id与input_hash导入：
market-voices --state ./state import-summary --input /private/path/summaries.json
market-voices --state ./state candidates --output /private/path/review-new.json
market-voices --state ./state approve-content --id ID --hash SUMMARY_HASH --reviewer your-name
market-voices --state ./state prepare --id edition-001
market-voices --state ./state approve-edition --id edition-001 --hash EDITION_HASH --reviewer your-name
market-voices --state ./state publish --edition edition-001
market-voices --state ./state export --output ./site-v1
```

发布批准绑定摘要/期刊hash。修改原文、日期或摘要后必须重新整理审核。统计由Python生成，读者仅显示结果。
自动模式允许通过来源及证据规则的候选进入当期；默认自动。可以
`mode manual`或`mode auto`切换；自动连续3窗口无合格新内容后切换manual，恢复需明确操作。

备用稿：逐条审核内容后`prepare --id backup-001 --backup --items ID1 ID2`，再批准期刊。
至少准备6份**真实审核**的备用稿；`status`给出库存是否达标。备用稿按旧日期展示、不进入当前多空榜。
人工模式仍采集/整理，但不会自动发布新的未批准观点。没有新内容时使用已批准期刊/备用稿；
耗尽时保留上一版本并标注延迟。不会凭空创造备用稿。

修正与回滚：`withdraw --id ID --reason '原因'`会在下一次export时从所有归档移除该条；
`rollback --edition ID`仅允许恢复以前发布过且无被撤回条目的期刊。重新部署导出文件才改变线上网站。

## 5. 云端更新与开源

[部署指南](docs/DEPLOYMENT.md)描述GitHub Pages、私有状态仓库、Secrets、预算与调度。
每个交易日开盘前1h、实际收盘后1h更新，处理DST/休市/提前收盘；约15分钟是目标，不是调度SLA。
网站只发布静态白名单，**禁止部署本地/private管理服务**。本机关闭不影响已部署网站阅读。

[契约](docs/CONTRACT.md) · [运营与故障处理](docs/OPERATIONS.md) ·
[AI产品案例与评测](docs/PRODUCT-CASE.md) · [第三方依赖](THIRD_PARTY.md)

开发检查：`pip install '.[dev]' && pytest -q`；`python -m build`生成独立wheel/sdist。
MIT仅覆盖此目录中自有代码，不覆盖第三方文章、字幕、商标或外部站点内容。

## 从旧MVP迁移

```bash
market-voices --state ./state migrate-inbox --input /private/path/inbox.sqlite3
market-voices --state ./state migrate-model --input /private/path/old-model.json --output /private/path/new-model.json
```

迁移只读取指定文件，旧资料保持不变；来源默认未核验、内容未批准。模型配置仅复制明确的四项字段，
新文件0600且拒绝覆盖；需另补费率快照。可以先在新工具中复核，再决定是否替代旧版工作台。
不要把迁移后的state或配置放进公开仓库。
