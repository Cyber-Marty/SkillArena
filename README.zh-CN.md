# SkillArena

**在相同任务上比较不同版本的 Skill，并保留每次运行的核查材料。**

SkillArena 是本地基准测试工具。v0.2 让真实的 Codex Agent 通过受限文件工具完成任务，对比三种条件：无 Skill（`baseline`）、初版 Skill（`v1`）和修订版 Skill（`v2`）。内置数据处理套件包含 10 个原创合成任务。结果只适用于这套任务和运行配置，不能外推为真实工作场景中的整体表现。

## 当前证据

**v0.2 的正式实验尚待运行。** [完整实验配置](examples/agent_suite.yaml)安排 10 个任务 × 3 种条件 × 1 次重复，共 30 次 Agent 运行；本文暂不报告其成绩。此前单独进行的[真实模型 Python 修错试验](research/gpt6-sol-high-2026-10-14/README.md)在有无 Skill 时均为 3/3 通过，但任务和运行协议不同，不能当作数据套件的结果。[确定性演示](examples/demo.yaml)中的 0% → 100% 来自脚本，不是模型效果。

## 安装与离线预览

需要 Python 3.11+，请从可信的源码检出安装。本项目尚未发布到 PyPI。

```bash
git clone https://github.com/Cyber-Marty/SkillArena.git
cd SkillArena
python -m venv .venv
# 根据所用终端激活 .venv。
python -m pip install -e .
skillarena plan examples/agent_suite.yaml
```

`plan` 只读取配置并输出预定顺序及预算，**不会调用模型**。[六次运行的预检配置](examples/agent_smoke.yaml)覆盖两个任务和三种条件，仅用于确认环境。

## 运行与核查

正式运行需要已用现有 ChatGPT 账户登录、且支持 `gpt-6-sol` 高推理强度及严格配置参数的新版 Codex CLI。若 `PATH` 指向旧版，可用 `SKILLARENA_CODEX_BIN` 指定新版可执行文件。

```bash
skillarena doctor
skillarena run examples/agent_smoke.yaml --execute --output results/agent-smoke
skillarena run examples/agent_suite.yaml --execute --output results/agent-suite
skillarena verify results/agent-suite
skillarena compare results/agent-suite --left v1 --right v2
skillarena report results/agent-suite/metrics.json --output results/agent-suite-view.html
```

每次运行都要使用新的输出目录。v0.2 实验必须显式加 `--execute`。完整配置上限为 30 次 Agent 运行，每次最多 40 次工具调用、180 秒。`doctor` 和运行过程会检查现有 ChatGPT 登录及套餐内额度；检测到 API 凭据、自定义端点、可用或状态不明的付费额度，以及不足或状态不明的套餐内额度时，会停止模型运行。它是本地的额外付费防护，**并非独立的账户账单审计**；允许的运行仍会消耗套餐内用量，工具不会购买额度。

Agent 只能列出和读取任务文件、写入 `output.json`、检查该文件的 JSON 语法，以及列出或读取所提供的 Skill。Shell、联网和任意代码执行被禁用。Skill 由 Agent 明确调用 `list_skills`、`read_skill` 获取；这项实验不测试 Codex 原生的隐式 Skill 路由。`check_output` 只检查语法与类型，正确性由 Agent 退出后的可信验证器判定。

[数据处理套件](benchmarks/data_workflows/README.md)覆盖 CSV 清理、去重、分组汇总、十进制金额、时区转换、关联、缺失值与零值、稳定排名、对账和 JSON 结构验证。每项任务都测试正确答案可通过验证器、至少一种合理的错误答案会被拒绝。输入均为原创合成数据，采用 MIT 许可；这些检查不构成独立的真实场景有效性证明。

v0.2 的结果目录包含任务与 Skill 快照、计划、环境摘要、逐次模型事件、工具审计、输出、评分、指标、HTML 报告及文件哈希清单。`skillarena verify` 离线检查文件自封存后是否变化，**不能证明运行真实发生或已由第三方复现**。重新生成报告或保存比较结果时，请把输出放在封存目录之外。详见[方法说明](docs/methodology.md)及[证据包指南](docs/result-bundle.md)。

同名及相关项目包括 [SkillsBench](https://github.com/benchflow-ai/skillsbench) 和 [Jiaqi Liu 的 SkillArena 数据集与框架](https://huggingface.co/datasets/JiaaqiLiu/SkillArena-datasets)。本仓库与它们无隶属关系。项目采用 MIT 许可；贡献要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。
