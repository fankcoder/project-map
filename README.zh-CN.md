# Project Map

[English](README.md) | [简体中文](README.zh-CN.md)

Project Map 是一个本地 Codex 插件，用于帮助智能体快速熟悉陌生代码仓库。它会生成 Markdown 架构索引，并在再次使用前验证索引是否仍与当前源码一致。

分析器仅使用 Python 标准库，不依赖第三方包，也不会导入或执行目标项目代码。

## 在 Codex 中安装和使用

Project Map 是一个只包含 Skill 的插件：在本地运行，不需要 API key 或 MCP 连接，也不会上传源码。常规 GitHub 安装方式是注册仓库 marketplace：

```bash
codex plugin marketplace add fankcoder/project-map
codex plugin marketplace list
```

启动 `codex`，输入 `/plugins`，选择 **Project Map Development** 并安装 `project-map`。安装或更新插件后需要开启一个新的 Codex 会话，Codex 才会发现插件包含的技能。目前 Codex CLI 和 ChatGPT 桌面应用支持插件，IDE 扩展暂不支持。

发布新版本后，可以运行 `codex plugin marketplace upgrade project-map-local` 刷新 marketplace，再进入 `/plugins` 检查插件，并重新开启一个新会话。

在希望 Codex 修改的项目中，可以直接发送：

```text
使用 $project-map 熟悉当前仓库，先验证或更新项目地图，再解释相关架构，然后开始修改。
```

插件也可以在 Codex 需要理解陌生仓库时自动触发。它会先验证已有地图，过期时进行增量更新，并且在修改前要求读取当前源码。需要稳定、明确地触发时，使用 `$project-map`。

### 推荐的 Codex 工作流

1. 在 Codex 中打开目标仓库；安装或更新插件后开启新的会话。
2. 首条消息使用：`使用 $project-map 在修改前检查这个仓库。`
3. 先让 Codex 总结地图中的 Snapshot、Changes Since Previous Map、Components 和 Entry Points。
4. 对于具体任务，给出功能或路径，例如：`使用项目地图定位认证流程，然后读取当前源码和测试。`
5. 进行结构性修改前，让 Codex 再次验证地图，过期时执行更新。
6. 切换分支、rebase 或完成较大改动后，发送：`更新项目地图，先总结新增、变化和删除的文件，再继续任务。`

项目地图是缩小搜索范围的导航索引，不是源码审查的替代品。好的提示词应该要求 Codex 先使用地图定位，再回读当前源码和测试确认行为。

### 本地开发和测试插件

如果要测试本地 checkout，而不是 GitHub 版本：

```bash
codex plugin marketplace add /absolute/path/to/project-map
codex plugin marketplace list
```

进入 `/plugins`，安装本地的 **Project Map Development**，修改插件文件后重新开启 Codex 会话。

## 直接使用命令行

```bash
python3 scripts/project_map.py map /path/to/repository
python3 scripts/project_map.py update /path/to/repository
python3 scripts/project_map.py check /path/to/repository
```

默认输出位于目标仓库内：

```text
.codex/project-map.md
.codex/project-map.manifest.json
```

如果地图仅供个人使用，可以把这些 `.codex/` 文件加入 `.gitignore`；如果团队需要共享项目导航文档，也可以将它们提交到仓库。

生成的 Markdown 会限制内容规模以节省 token，其中包含组件概览、经过过滤的文件树、入口点、本地依赖树、修改热点和公开符号。即使部分展示内容因上限被省略，manifest 仍会记录每个已索引源码文件的哈希，因此不会因省略内容而漏掉过期状态。

`update` 会将当前 Git commit 和工作区与上一次 manifest 进行比较，再用 SHA-256 验证文件内容。它只重新解析新增或变化的文件，并复用未变化文件的分析缓存。更新后的地图还会简要列出自上次生成以来新增、变化和删除的文件。如果缓存缺失或版本不兼容，命令会安全地回退到完整生成。

## 支持的分析信息

- Git 仓库优先分析 Git 跟踪的文件；非 Git 项目会安全地回退到文件系统扫描。
- 通过 `ast` 分析 Python 模块、导入、类、函数、方法、文档字符串和行号范围。
- 使用保守的标准库解析方式分析 JavaScript 和 TypeScript 的导入、导出、类、函数和行号。
- 识别 `pyproject.toml`、`package.json`、`Cargo.toml`、`manage.py` 和 `__main__.py` 等常见项目元数据及入口文件。
- manifest 保存分析器版本、Git commit、文件哈希、可复用的分析缓存和生成时间。
- 在存在声明版本时读取 `pyproject.toml`、`package.json` 或 `Cargo.toml` 中的项目版本。

项目地图是导航索引，不是源码事实的替代品。验证器发现变化时会明确报告地图已经过期，而不会继续静默信任旧内容。实际修改代码前，仍应读取地图指向的当前源码文件。

## 后续规划

当前版本重点是可信、低成本的项目地图。后续建议拆成独立工作流，而不是把所有功能塞进一个庞大的 Skill：

- 按任务生成 context pack，只返回与请求相关的模块、符号、测试和依赖。
- 影响分析，列出反向依赖、可能的入口、受影响测试和修改风险。
- 分层 Markdown 地图，先读取小型索引，需要时再打开组件详情。
- 架构规则，在 CI 或结构性修改前检测禁止的依赖方向。

以上是后续设计方向，不代表当前版本已经提供这些功能。

## 插件目录结构

根目录的 `plugin.json` 是 Codex 使用的可移植 Agent Plugins 清单，`.codex-plugin/plugin.json` 是兼容性回退清单。`skills/project-map/SKILL.md` 定义 Codex 应在何时以及如何使用项目地图，`scripts/project_map.py` 是具体的分析与验证实现。

插件打包和安装规范请参阅 [OpenAI 官方插件指南](https://developers.openai.com/plugins/build/plugins)。
