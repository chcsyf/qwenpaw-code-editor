# 变更记录

## v0.1.5（2026-08-14）

- **Robot Framework 语法高亮**：新增 `.robot` / `.resource` 扩展名支持（语言 id
  `robotframework`，Monarch tokenizer 自定义实现）——覆盖 `*** 区块标题 ***`（Settings/
  Variables/Test Cases/Tasks/Keywords 等）、`[Documentation]` `[Tags]` 等方括号设置、
  `${var}` `@{list}` `&{dict}` `%{env}` 变量、`#` 注释与表格 `|` 分隔符，并对关键字调用
  着色。与 QwenPaw 2.1.0 官方 Files Workspace 的 Robot Framework 支持（#6519）对齐
- **OS Shell 窗口化声明**：`launch_scope` 由 `page` 改为 `window`——2.1.0 OS 桌面中作为
  可移动/可调整大小窗口打开；2.0.1 不识别 `window` 值时自动回退 page 内嵌（功能不受影响，
  渐进增强，无需改动其他代码）
- **同步修复 plugin.py 版本号滞后**：`PLUGIN_VERSION` 原为 0.1.2（v0.1.3/v0.1.4 仅更新了
  plugin.json 与前端），现统一为 0.1.5，与 plugin.json 一致

## v0.1.4（2026-08-12）

- **修复 v0.1.3 引入的加载卡死（严重 bug）**：直接配置 `vs/nls.availableLanguages['*']='zh-cn'`
  会导致 Monaco AMD loader 永久挂起、编辑器一直停在「正在加载 Monaco Editor」——这是
  monaco-editor 官方已知 bug（microsoft/monaco-editor#5402）：语言包 `vs/nls/lang/zh-cn.js`
  只设置 `_VSCODE_NLS_MESSAGES` 全局变量、不调用 `define()`，而 `nls.messages-loader` 用 AMD
  require 加载它，模块永远无法就绪。现改为：先把语言包当普通 `<script>` 预加载（全局变量生效），
  再手动 `define("vs/nls/lang/zh-cn", ...)` 注册该模块，使 nls 插件链正常完成——右键菜单中文
  汉化保留，同时编辑器加载恢复与英文版一致的速度。语言包加载失败时自动退回英文并用手动
  label 兜底，任何情况下都不再阻塞加载

## v0.1.3（2026-08-12）

- **右键菜单汉化改为官方 nls 语言包机制**：v0.1.2 的手动改 action label 方案无法覆盖
  Cut/Copy/Paste/更改所有匹配项/命令面板 等固定菜单项（由 ContextMenuController 内部创建），
  实际仍显示英文。现通过 `require.config` 配置 `vs/nls.availableLanguages['*']='zh-cn'`，
  让 Monaco 加载官方中文语言包（min/vs/nls/lang/zh-cn.js），右键菜单、命令面板、查找替换框等
  全部内置文本一次性汉化；手动改 label 仅作 CDN 语言包异常时的兜底

## v0.1.2（2026-08-12）

- **右键菜单汉化**：Monaco 内置右键菜单（剪切 / 复制 / 粘贴 / 全选 / 复制（带语法高亮）/
  命令面板 / 格式化 / 查找 / 替换 / 行注释 / 转到定义 等 60+ 项）改为中文——创建编辑器后
  遍历 action 修改 label，右键菜单实时读取生效
- **修复竞态：外部跳转目标偶尔被旧文件覆盖**——Monaco 就绪的 useEffect 原来无条件从
  `LS_FILE` 恢复文件，与初始化流程的 externalFile 打开并发时，后完成的 fetch 会覆盖先
  完成的（表现为从文件浏览器跳转过来打开的是上次的文件）。现引入 `externalTargetRef`，
  两个打开路径统一优先外部目标，消除并发冲突

## v0.1.1（2026-08-12）

- **外部跳转打开文件（文件浏览器「✏️ 编辑」联动）**：读取 `qwenpaw-code-editor:externalFile`
  localStorage 键（文件浏览器跳转前写入，读完即删），优先打开该文件并自动定位文件树到
  其所在目录；不再使用 `?file=` query（宿主 SPA 路由重写会丢弃 query）

## v0.1.0（2026-08-09）

- 侧边栏入口移入「插件」分组（parentId: plugins-group），点击直达编辑器
- 快捷访问区标题可折叠/展开，状态记忆；agent 条目不再重复显示 🤖 图标
- 文件树目录折叠箭头加大（▸/▾ fontSize 10→14）
- 新建文件保存后立即出现在文件树（无需手动刷新）；父目录未加载时自动加载展开
- 平台模式访问范围放宽：与 file-browser 一致，遵循系统权限（access_root 仅作默认树根）
- 文件树滚动条统一为暗色细条风格（与 Monaco 编辑器 / 平台其它面板一致）

## v0.0.1（2026-08-09）

首个正式版本：

- 基于 Monaco Editor（VSCode 同款编辑器核心，CDN 加载，无构建）
- 左侧文件树懒加载浏览目录，点击打开文件；目录折叠箭头清晰易点
- 20+ 语言语法高亮自动识别（按扩展名）
- Ctrl+S 保存 / 工具栏保存，未保存 ● 标记
- 新建文件（可带子路径）、目录刷新
- 侧边栏入口：注册于侧边栏最底部（与文件/终端插件并列，📝 代码编辑器），点击直达
- 快捷访问：左侧 ⚡ 快捷访问区（与文件插件一致）——WORKING_DIR、/tmp、/home、/root、各智能体工作区、NAS 根、/app、/，点击一键切换文件树根
- 打开位置缓存：展开目录链 / 当前打开文件 / 编辑器滚动位置 全部持久化，刷新页面后自动恢复
- 后端：/status /ls /read /write 四个接口，UTF-8 无损读写
- 访问控制：工作区模式仅限 WORKING_DIR；平台模式遵循系统权限（与 file-browser 一致），access_root 仅作默认树根；二进制 / 非 UTF-8 / 超大文件（>2MB）安全拦截
- 深色 GitHub Dark 主题，与其它 QwenPaw 插件一致
