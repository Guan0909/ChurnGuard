# ChurnGuard

用户流失预警与干预系统 —— 基于规则引擎 + LLM（DeepSeek V4）混合架构。

## 快速开始

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 项目结构

```
churnguard/
├── .trae/rules/project_rules.md   # 项目规则
├── app.py                         # 应用入口
├── config.py                      # 配置中心
├── engine/                        # 规则引擎 & 成本计算
├── llm/                           # LLM 客户端 & Prompt
├── ui/                            # Streamlit 页面
├── utils/                         # 工具模块
├── tests/                         # 测试
├── docs/                          # 文档
└── data/                          # 数据文件
```