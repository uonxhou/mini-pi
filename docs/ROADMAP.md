# mini-pi 开发路线图

> 基于 [pi](https://github.com/earendil-works/pi) 架构，从零实现一个 AI Coding Agent，用于学习 Agent 开发的各个核心组成部分。

---

## 总览

```
Phase 1  ████████████████████  ✅ 完成    核心 Agent 循环
Phase 2  ░░░░░░░░░░░░░░░░░░░░  ⬚ 待开始  测试体系
Phase 3  ░░░░░░░░░░░░░░░░░░░░  ⬚ 待开始  会话持久化
Phase 4  ░░░░░░░░░░░░░░░░░░░░  ⬚ 待开始  多 Provider & 鲁棒性
Phase 5  ░░░░░░░░░░░░░░░░░░░░  ⬚ 待开始  交互式 TUI
Phase 6  ░░░░░░░░░░░░░░░░░░░░  ⬚ 待开始  扩展系统
Phase 7  ░░░░░░░░░░░░░░░░░░░░  ⬚ 待开始  高级特性
```

---

## Phase 1：核心 Agent 循环 ✅

**目标**：跑通 "用户输入 → LLM → 工具调用 → 结果 → 再推理" 的最小闭环。

### 已完成

- [x] **类型系统** (`types.py`)
  - ContentBlock：text, image, thinking, tool_call, tool_result
  - Message：UserMessage, AssistantMessage, ToolResultMessage
  - ToolDefinition + JSON Schema 双向转换（Anthropic / OpenAI）
  - AgentEvent 流式事件
  - Usage 用量追踪

- [x] **LLM 客户端** (`llm/client.py`)
  - Anthropic API 封装（async + streaming）
  - 消息格式转换（内部格式 ↔ Anthropic 格式）
  - Tool call streaming（累积 partial JSON）
  - 错误处理

- [x] **工具系统** (`tools/`)
  - `read` — 读文件（文本 + 图片 base64，offset/limit 支持）
  - `bash` — Shell 执行（超时、输出截断、session 环境变量）
  - `write` — 创建/覆盖文件（自动创建父目录）
  - `edit` — 精确文本替换（唯一性校验、重叠检测、unified diff 输出）

- [x] **Agent 循环** (`agent/loop.py`)
  - 主循环：LLM 调用 → 工具执行 → 结果注入 → 再调用
  - 最大轮次保护（max_turns）
  - Token 用量累计
  - 流式事件产出

- [x] **CLI** (`cli.py`)
  - 单次模式：`mini-pi "问题"`
  - 交互模式：`mini-pi -i`（多轮对话、`!cmd` 快捷、`/help` 等）

### 关键学习点

| 概念 | 对应代码 | 要点 |
|------|---------|------|
| Tool Calling 协议 | `llm/client.py::chat_stream` | Anthropic 的 `tool_use` content block 如何流式传输 |
| System Prompt 工程 | `llm/client.py::DEFAULT_SYSTEM_PROMPT` | 如何引导 LLM 正确使用工具 |
| 精确编辑 | `tools/edit.py` | 通过 oldText 唯一匹配实现非破坏性编辑，这是 pi 的核心创新 |
| Agentic Loop | `agent/loop.py` | LLM 与工具之间的控制流设计 |

---

## Phase 2：测试体系 ⬚

**目标**：建立完整的测试套件，确保每次开发完成后可一键验证所有已有功能不受影响。

### 设计原则

- **不调 LLM**：所有测试使用 mock，不依赖外部 API，单测在毫秒级完成
- **分层测试**：单元测试（工具函数）→ 集成测试（Agent 循环）→ 端到端测试（CLI）
- **回归保护**：每完成一个 Phase 的开发，同步补齐该 Phase 的测试
- **一键运行**：`uv run pytest` 跑通全量测试

### 计划任务

- [ ] **测试基础设施**
  - 安装 `pytest` + `pytest-asyncio` + `pytest-cov`
  - 创建 `tests/` 目录，镜像 `src/mini_pi/` 结构
  - 配置 `pyproject.toml` 中的 pytest 选项

- [ ] **类型层测试** (`tests/test_types.py`)
  - `ToolDefinition.to_anthropic_schema()` 输出格式验证
  - `ToolDefinition.to_openai_schema()` 输出格式验证
  - `UserMessage` / `AssistantMessage` / `ToolResultMessage` 序列化
  - `AgentEvent` 各类型构造

- [ ] **工具层测试** (`tests/tools/`)
  - `test_read.py`：文本文件读取、图片检测、offset/limit 截断、文件不存在、权限错误
  - `test_bash.py`：命令执行、超时、输出截断、退出码、环境变量注入
  - `test_write.py`：新建文件、覆盖文件、父目录创建、权限错误
  - `test_edit.py`：单次替换、多次编辑、唯一性校验、重叠检测、diff 输出

- [ ] **LLM Mock 层** (`tests/mocks.py`)
  - `MockLLMClient`：模拟 Anthropic API 流式响应
  - 支持预设文本响应（`set_text_response("hello")`）
  - 支持预设 tool call 序列（`set_tool_responses([...])`）
  - 模拟错误（API 错误、超时、JSON 解析失败）

- [ ] **Agent 循环测试** (`tests/test_agent.py`)
  - 纯文本响应：发 prompt → 收 text 事件 → agent_done
  - 单轮 tool call：发 prompt → tool_call 事件 → 工具执行 → agent_done
  - 多轮 tool call：连续多个 tool call，验证消息历史正确累积
  - max_turns 限制：达到上限后正确终止
  - 错误处理：LLM 返回错误时 agent 正确处理
  - Token 用量累计正确

- [ ] **CLI 集成测试** (`tests/test_cli.py`)
  - 参数解析：`-i`, `-m`, `-c` 各参数
  - 无 API Key 时优雅报错
  - `--help` 输出

- [ ] **CI 就绪**
  - `uv run pytest` 可在任何机器上零配置运行
  - 后续可接入 GitHub Actions 自动测试

### 关键学习点

| 概念 | 要点 |
|------|------|
| Mock 策略 | 如何在不调真实 API 的前提下测试 Agent 完整链路 |
| Async 测试 | `pytest-asyncio` 的 fixture 和 event loop 管理 |
| 工具测试设计 | 文件系统隔离（tmp_path）、边界条件、错误路径 |
| 流式 Mock | 用 `asyncio.Queue` 或 async generator 模拟 SSE 流 |

**目标**：实现 pi 的 JSONL 树形会话存储，支持会话恢复和分支。

### 计划任务

- [ ] **会话数据模型** (`session/format.py`)
  - SessionEntry 基类（id, parentId, timestamp）
  - 入口类型：session header, message, compaction, branch_summary, label, custom
  - 树形结构：通过 id/parentId 形成多分支链
  - JSONL 读写（逐行序列化、增量追加）

- [ ] **SessionManager** (`session/manager.py`)
  - 静态工厂：`create()`, `open()`, `continue_recent()`, `in_memory()`, `list()`
  - 追加方法：`append_message()`, `append_compaction()`, `append_label()` 等
  - 树导航：`branch()`, `get_path()`, `get_children()`, `get_leaf()`
  - 上下文构建：`build_context_entries()` — 从叶子回溯 + 处理 compaction

- [ ] **Compaction（上下文压缩）** (`session/compaction.py`)
  - 触发条件：token 超限 / 手动触发
  - 策略：保留最近 N 条消息，摘要旧消息
  - 摘要生成：调用 LLM 生成结构化摘要
  - 格式：compaction entry 含 summary + firstKeptEntryId + retainedTail

- [ ] **CLI 集成**
  - `--continue` / `-c`：继续最近的 session
  - `--resume` / `-r`：浏览并选择 session
  - `--session <path>`：指定 session 文件
  - `/tree` 命令：在会话历史中导航

### 关键学习点

| 概念 | 要点 |
|------|------|
| 事件溯源模式 | 每次操作作为不可变 entry 追加，完整可回放 |
| 树形分支 | id/parentId 实现原地分支，无需复制文件 |
| 上下文窗口管理 | Compaction 是长对话 Agent 的必要组件 |
| JSONL 格式 | 每行一个 JSON 对象，可增量读写，比单一 JSON 更适合流式追加 |

---

## Phase 3：会话持久化 ⬚

**目标**：实现 pi 的 JSONL 树形会话存储，支持会话恢复和分支。

### 计划任务

- [ ] **会话数据模型** (`session/format.py`)
  - SessionEntry 基类（id, parentId, timestamp）
  - 入口类型：session header, message, compaction, branch_summary, label, custom
  - 树形结构：通过 id/parentId 形成多分支链
  - JSONL 读写（逐行序列化、增量追加）

- [ ] **SessionManager** (`session/manager.py`)
  - 静态工厂：`create()`, `open()`, `continue_recent()`, `in_memory()`, `list()`
  - 追加方法：`append_message()`, `append_compaction()`, `append_label()` 等
  - 树导航：`branch()`, `get_path()`, `get_children()`, `get_leaf()`
  - 上下文构建：`build_context_entries()` — 从叶子回溯 + 处理 compaction

- [ ] **Compaction（上下文压缩）** (`session/compaction.py`)
  - 触发条件：token 超限 / 手动触发
  - 策略：保留最近 N 条消息，摘要旧消息
  - 摘要生成：调用 LLM 生成结构化摘要
  - 格式：compaction entry 含 summary + firstKeptEntryId + retainedTail

- [ ] **测试补齐**
  - `tests/session/`：JSONL 读写、树导航、compaction 逻辑

- [ ] **CLI 集成**
  - `--continue` / `-c`：继续最近的 session
  - `--resume` / `-r`：浏览并选择 session
  - `--session <path>`：指定 session 文件
  - `/tree` 命令：在会话历史中导航

### 关键学习点

| 概念 | 要点 |
|------|------|
| 事件溯源模式 | 每次操作作为不可变 entry 追加，完整可回放 |
| 树形分支 | id/parentId 实现原地分支，无需复制文件 |
| 上下文窗口管理 | Compaction 是长对话 Agent 的必要组件 |
| JSONL 格式 | 每行一个 JSON 对象，可增量读写，比单一 JSON 更适合流式追加 |

---

## Phase 4：多 Provider & 鲁棒性 ⬚

**目标**：抽象 LLM Provider 层，支持 OpenAI；增加重试、错误恢复。

### 计划任务

- [ ] **Provider 抽象层** (`llm/providers/`)
  - `BaseProvider` 抽象基类
    - `chat_stream()` — 流式对话
    - `supports_tools()` — 是否支持 tool calling
    - `supports_images()` — 是否支持图片
  - `AnthropicProvider` — 重构现有代码为 provider 实现
  - `OpenAIProvider` — OpenAI Chat Completions API
  - Provider 注册 & 发现机制

- [ ] **消息格式适配层**
  - 统一的内部消息格式
  - Anthropic ↔ 内部 ↔ OpenAI 格式双向转换
  - 处理格式差异（如 Anthropic 的 tool_result 是 user message，OpenAI 的 tool role）

- [ ] **Model 注册表** (`llm/models.py`)
  - Model 元数据（context_window, max_tokens, cost, reasoning 支持）
  - Provider 关联
  - 模型列表查询 & 过滤

- [ ] **鲁棒性增强** (`agent/retry.py`)
  - API 错误重试（指数退避）
  - 上下文溢出检测 & 自动 compaction 触发
  - Tool 执行超时处理
  - 部分失败恢复（一个 tool 失败不影响其他 tool）

- [ ] **CLI 增强**
  - `--provider` / `--model` 参数
  - `/model` 命令切换模型
  - 模型信息展示

### 关键学习点

| 概念 | 要点 |
|------|------|
| Provider 适配器模式 | 不同 API 的差异如何抽象为统一接口 |
| Anthropic vs OpenAI tool calling | Anthropic 使用 content block，OpenAI 使用独立 tool_calls 字段 |
| 重试策略 | 指数退避、错误分类（可重试 vs 不可重试） |
| 上下文溢出处理 | 动态检测 + 自动 compaction |

---

## Phase 5：交互式 TUI ⬚

**目标**：用 Textual 构建类似 pi 的终端交互界面。

### 计划任务

- [ ] **TUI 框架选型 & 搭建** (`tui/`)
  - Textual — Python 生态中最成熟的 TUI 框架
  - 备选：Rich（轻量）或直接用 ANSI 序列
  - 基础布局：header / messages / input / footer

- [ ] **消息渲染**
  - 用户消息、助手消息、工具调用的差异化展示
  - Markdown 渲染（代码块高亮）
  - 流式文本逐字输出
  - Thinking blocks 折叠/展开

- [ ] **编辑器**
  - 多行输入（Shift+Enter）
  - 文件路径补全（@ 触发）
  - 命令模式（/ 触发）
  - 历史记录（上下箭头）

- [ ] **组件系统**
  - Header：model info, session name
  - Footer：token usage, cost, working directory
  - Status line：扩展状态
  - 快捷键注册 & 绑定（Ctrl+C 清除, Ctrl+L 切换模型）

- [ ] **交互功能**
  - `/tree`：树形会话导航
  - `/settings`：设置面板
  - Tool output 折叠 (Ctrl+O)
  - 消息队列（steering / follow-up）

### 关键学习点

| 概念 | 要点 |
|------|------|
| TUI 架构 | 事件驱动、组件化布局 vs Web 的 DOM 差异 |
| 流式渲染 | 如何在终端中实现逐字输出而不闪烁 |
| 输入处理 | keybindings、多行输入、补全 |
| 异步 UI | TUI 事件循环与 Agent 事件循环的协调 |

---

## Phase 6：扩展系统 ⬚

**目标**：实现 pi 的事件驱动 Extension 机制，让 Agent 行为可定制。

### 计划任务

- [ ] **事件总线** (`extension/events.py`)
  - 生命周期事件：`session_start`, `session_shutdown`, `resources_discover`
  - Agent 事件：`before_agent_start`, `agent_start`, `agent_end`
  - Turn 事件：`turn_start`, `turn_end`
  - Tool 事件：`tool_call`（可拦截）, `tool_result`（可修改）
  - Message 事件：`message_start`, `message_update`, `message_end`
  - Input 事件：`input`（可拦截/转换）

- [ ] **Extension API** (`extension/api.py`)
  - `pi.registerTool()` — 注册自定义工具
  - `pi.registerCommand()` — 注册 / 命令
  - `pi.registerShortcut()` — 注册快捷键
  - `pi.on(event, handler)` — 事件订阅
  - `ctx.ui` — 用户交互（notify, confirm, select, input）

- [ ] **Extension 加载** (`extension/loader.py`)
  - 自动发现：`~/.mini-pi/extensions/`、`.mini-pi/extensions/`
  - CLI 加载：`-e ./path.ts` 对应
  - 热重载
  - 加载顺序 & 依赖管理

- [ ] **示例扩展**
  - `permission-gate`：拦截危险 bash 命令
  - `git-checkpoint`：每轮自动 git stash
  - `custom-tool`：注册一个自定义 API 调用工具

### 关键学习点

| 概念 | 要点 |
|------|------|
| 中间件模式 | 事件处理链、拦截器、修改器 |
| 插件架构 | 自动发现、隔离、热重载 |
| 控制反转 | Extension 如何扩展核心行为而不修改核心代码 |

---

## Phase 7：高级特性 ⬚

**目标**：补完 pi 生态的剩余部分。

### 计划任务

- [ ] **Skills 系统** (`skills/`)
  - SKILL.md 格式解析
  - 自动发现（全局 + 项目 + 包）
  - `/skill:name` 命令触发
  - LLM 自动按需加载

- [ ] **Prompt Templates** (`prompts/`)
  - Markdown 模板解析
  - 变量插值 `{{variable}}`
  - `/templatename` 命令展开

- [ ] **Pi Packages** (`packages/`)
  - 打包规范（extensions + skills + prompts + themes）
  - Git 安装
  - 版本管理

- [ ] **Context Files** (`context/`)
  - AGENTS.md / CLAUDE.md 自动发现
  - 目录树向上遍历
  - 合并策略

- [ ] **Settings 系统** (`settings/`)
  - 全局 + 项目级配置合并
  - 常用选项：thinking level, compaction, retry
  - 热更新

- [ ] **MCP 集成**（Model Context Protocol）
  - MCP Server 客户端
  - 工具自动注册

### 关键学习点

| 概念 | 要点 |
|------|------|
| 声明式技能 | 通过 Markdown 定义 Agent 能力，而非代码 |
| 配置合并 | 全局 → 项目 的层级覆盖模式 |
| 协议集成 | MCP 作为外部工具的标准协议 |

---

## 可选方向

以下方向取决于学习兴趣，可在任意阶段插入：

| 方向 | 描述 | 前置 |
|------|------|------|
| **Sub-agents** | 多 Agent 协作，task 分发 | Phase 6 |
| **Sandbox** | Docker/SSH 隔离执行 bash | Phase 4 |
| **Plan Mode** | 先制定计划再执行 | Phase 6 |
| **RPC Mode** | JSON-RPC 进程间集成 | Phase 4 |
| **SDK** | 以库的形式嵌入其他应用 | Phase 3 |
| **Web UI** | 浏览器端界面（FastAPI + WebSocket） | Phase 5 |
| **Cost Tracking** | 详细的 token 费用统计 | Phase 4 |

---

## 学习资源

- [pi 源码](https://github.com/earendil-works/pi-mono) — 参考实现
- [pi 文档](https://github.com/earendil-works/pi) — 架构说明
- [Agent Skills 标准](https://agentskills.io) — Skill 规范
- [Anthropic Tool Use 文档](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — Tool Calling 最佳实践
- [Textual 文档](https://textual.textualize.io/) — Python TUI 框架
