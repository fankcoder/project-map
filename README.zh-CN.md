# Project Map

[English](README.md) | [简体中文](README.zh-CN.md)

Project Map 是一个本地 Codex 插件，用于帮助智能体快速熟悉陌生代码仓库。它会生成 Markdown 架构索引，并在再次使用前验证索引是否仍与当前源码一致。

分析器仅使用 Python 标准库，不依赖第三方包，也不会导入或执行目标项目代码。

## 在 Codex 中安装

本仓库在 `.agents/plugins/marketplace.json` 中提供了一个仓库级 marketplace。克隆仓库后，注册这个本地 marketplace：

```bash
codex plugin marketplace add /absolute/path/to/project-map
codex plugin marketplace list
```

启动 `codex`，输入 `/plugins`，选择 **Project Map Development** 并安装 `project-map`。安装后需要开启一个新的 Codex 会话，Codex 才会发现插件包含的技能。目前 Codex CLI 和 ChatGPT 桌面应用支持插件，IDE 扩展暂不支持。

安装后可以通过 `$project-map` 明确调用，也可以在 Codex 需要理解陌生仓库时由其自动发现。插件会先验证已有地图，只有地图过期时才在架构分析前重新生成。

## 直接使用命令行

```bash
python3 scripts/project_map.py map /path/to/repository
python3 scripts/project_map.py check /path/to/repository
```

默认输出位于目标仓库内：

```text
.codex/project-map.md
.codex/project-map.manifest.json
```

如果地图仅供个人使用，可以把这些 `.codex/` 文件加入 `.gitignore`；如果团队需要共享项目导航文档，也可以将它们提交到仓库。

生成的 Markdown 会限制内容规模以节省 token，其中包含组件概览、经过过滤的文件树、入口点、本地依赖树、修改热点和公开符号。即使部分展示内容因上限被省略，manifest 仍会记录每个已索引源码文件的哈希，因此不会因省略内容而漏掉过期状态。

## 支持的分析信息

- Git 仓库优先分析 Git 跟踪的文件；非 Git 项目会安全地回退到文件系统扫描。
- 通过 `ast` 分析 Python 模块、导入、类、函数、方法、文档字符串和行号范围。
- 使用保守的标准库解析方式分析 JavaScript 和 TypeScript 的导入、导出、类、函数和行号。
- 识别 `pyproject.toml`、`package.json`、`Cargo.toml`、`manage.py` 和 `__main__.py` 等常见项目元数据及入口文件。
- manifest 保存分析器版本、Git commit、文件哈希和生成时间。
- 在存在声明版本时读取 `pyproject.toml`、`package.json` 或 `Cargo.toml` 中的项目版本。

项目地图是导航索引，不是源码事实的替代品。验证器发现变化时会明确报告地图已经过期，而不会继续静默信任旧内容。实际修改代码前，仍应读取地图指向的当前源码文件。

## 插件目录结构

根目录的 `plugin.json` 是 Codex 使用的可移植 Agent Plugins 清单，`.codex-plugin/plugin.json` 是兼容性回退清单。`skills/project-map/SKILL.md` 定义 Codex 应在何时以及如何使用项目地图，`scripts/project_map.py` 是具体的分析与验证实现。

插件打包和安装规范请参阅 [OpenAI 官方插件指南](https://developers.openai.com/plugins/build/plugins)。
