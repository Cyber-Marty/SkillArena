# SkillArena

**Skill 真的能提升 AI Agent 的表现吗？** SkillArena 在相同任务的独立副本上运行「不使用 Skill」和「使用 Skill」两组实验，保存每次输出、评价记录和 HTML 报告。

## 第一项真实模型实验

2026 年 10 月 14 日，我们用 **GPT-6 Sol、High 推理强度**测试了一个小型 Python 边界错误。任务代码是自建样例，模型调用是真实的，使用现有 ChatGPT 登录，没有使用 API Key。

| 条件 | 通过次数 | 平均输入 token | 平均运行时间 |
| --- | ---: | ---: | ---: |
| 无 Skill | 3/3 | 14,457 | 34.9 秒 |
| 有 Skill | 3/3 | 14,507 | 46.7 秒 |

**成功率差值为 0 个百分点。** 这个任务对模型较简单，三组配对实验不能证明 Skill 在其他任务上无效，也不能据此判断运行时间差异。实验方法、原始指标和逐次证据见[研究记录](research/gpt6-sol-high-2026-10-14/README.md)。

## 五分钟上手

需要 Python 3.11+：

```bash
git clone https://github.com/Cyber-Marty/SkillArena.git
cd SkillArena
python -m venv .venv
# 根据所用终端激活 .venv
python -m pip install -e .
skillarena run examples/demo.yaml --output results/demo
```

打开 `results/demo/report.html`。同一目录还包含 `metrics.json`、`logs/` 和每次运行的 `artifacts/`。

**注意：** `examples/demo.yaml` 使用确定性脚本演示工具流程，显示的 0% → 100% 并非真实模型效果。真实模型实验使用 `examples/real_codex.yaml`，需要已登录 ChatGPT 的新版 Codex CLI；适配器会拒绝 API Key 登录。

项目仍处于早期阶段，当前支持 YAML 定义、本地独立运行、命令适配器、退出码评价和可分享报告。完整方法和贡献方式见英文 [README](README.md)、[方法文档](docs/methodology.md)与[贡献指南](CONTRIBUTING.md)。
