<p align="center">
  <img src="resources/peach-logo.png" alt="Peach" width="96">
</p>

<h1 align="center">Peach</h1>

直接播放按浏览器对片源实际容器、视频 profile 与音频组合的报告协商，覆盖可用的 HEVC／H.265、H.264、AV1、VP8／VP9 等编码；不支持时保留兼容转换与失败回退。浏览与播放设置提供默认关闭的按需拖动预览，直接在浏览器解码非计费本地影片的悬停帧，仅使用小型内存缓存，不生成时间轴文件。

时间轴预览提供关闭、每 10 秒、每 30 秒与自定义 1–3600 秒间隔；可选 CPU、CUDA 或实验 Vulkan 解码，硬件不可用时回退 CPU。媒体库设置提供转码缓存目录和总容量上限。播放器根据客户端 AV1 能力优先直读兼容 MP4，统计面板展示编码、播放方式与转换依据；卡片悬停不启动整片转码。

缩略图采集可在任务浮层或数据管理页选择低占用、标准、全速，独立于扫描速度和采样密度。默认低占用；任务结束后运行面板自动隐藏。

时间轴缩略图任务显示独立进度与停止按钮，FFmpeg 按所选速度分配线程，任务取消后回收自身子进程。播放器拖动预览按单格裁切图集，支持恢复播放和末张不足十行的预览图。详情见[性能选项与验证范围](docs/PERFORMANCE.md)。

定制版本在关注管理提供 RSS 图文列表，展示主缩略图、全部预览图及带 AllDebrid／Real-Debrid 图标的下载链接。每个订阅可隐藏不支持的链接。在下载渠道保存密钥及可选目录；容器目录用于服务端下载，留空交给浏览器。设计边界见 [RSS 下载决策](docs/adr/0116-rss-debrid-downloads.md)。

关注页的「全部」包含 RSS 更新。每条 RSS 订阅可独立开启自动更新并设置间隔，默认 6 小时；关闭自动更新仍保留已取得条目，并可手工检查更新。

RSS 来源可单独设置永久保存，或按天、月、年保留已保存条目；期限从首次保存起算，刷新不延长。同一订阅中的稳定条目标识或相同文章地址合并为一条，下载链接与预览合并保留。到期清退条目内容，保留最小去重记忆，已下载文件不动。图片与链接保存地址，原站仍需提供相应资源。

debrid 下载沿用后台任务浮层，跨页展示传输与导入进度，可取消并重试导入。每个下载渠道可启用「完成后扫描导入」；目录须位于已配置媒体库内，Docker 使用容器路径。完成的文件通过单条摄取与持久后继进入定向资料处理；资料失败保留文件，重启继续排队任务。浏览器直接下载由浏览器管理，服务端字节进度及自动导入用于配置目录的下载。

下载渠道可设置最大同时下载数（每个渠道默认 3，范围 1–10），用于服务端目录下载。等待中的文件在有空位时自动开始；RSS 单文件下载请求由服务端保存并接续，不依赖网页保持打开。浏览器下载并发由浏览器管理。

并发设置保存后读取服务端确认结果。下载浮层保留已完成状态，「清除已结束」隐藏结束记录并保留文件和下载凭据；仍在导入的记录继续显示。RSS 每页默认显示 20 条，可选择 10、20、50 或 100 条并翻页，浏览器保存该选择。

「浏览与播放」提供默认关闭的视频缓冲与快速界面实验开关；播放器记住本机音量和静音，四向跳转在时间滑条获得焦点时仍使用已设置步长。研究依据、流量取舍与验证范围见[实验性能选项](docs/PERFORMANCE.md)。

<p align="center">给自己用的私人影片馆藏：本地硬盘、网盘和关注的创作者，放在一个地方看。</p>

<p align="center">
  <a href="https://peach.video">官网</a> ·
  <a href="https://github.com/peach-mitao/peach/releases">下载安装包</a> ·
  <a href="https://demo.peach.video">在线演示</a> ·
  <a href="https://github.com/peach-mitao/peach/releases/tag/intro-video">介绍视频</a> ·
  <a href="https://github.com/peach-mitao/peach/issues">问题反馈</a> ·
  <a href="https://github.com/orgs/peach-mitao/projects/7/views/1">需求看板</a> ·
  <a href="https://github.com/orgs/peach-mitao/projects/7/views/3">路线图</a> ·
  <a href="#文档">文档</a> ·
  <a href="README.en.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/peach-mitao/peach/releases"><img src="https://img.shields.io/github/v/release/peach-mitao/peach?include_prereleases&amp;filter=v*&amp;sort=semver&amp;display_name=tag" alt="release"></a>
  <a href="https://github.com/peach-mitao/peach/actions/workflows/test.yml"><img src="https://img.shields.io/github/actions/workflow/status/peach-mitao/peach/test.yml?branch=master&amp;label=tests&amp;logo=githubactions&amp;logoColor=white" alt="CI 状态"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0--or--later-blue?logo=gnu&amp;logoColor=white" alt="license"></a>
  <a href="docs/TESTING_DESKTOP.md"><img src="https://img.shields.io/badge/Windows-x64-0078D4" alt="Windows x64"></a>
  <a href="docs/OPERATIONS.md#macos-独立测试包"><img src="https://img.shields.io/badge/macOS-DMG-555555?logo=apple&amp;logoColor=white" alt="macOS 独立应用构建与安装"></a>
  <img src="https://img.shields.io/badge/18%2B-adult%20content-critical" alt="18+ 成人内容">
</p>

https://github.com/user-attachments/assets/a5610874-e611-41bb-be22-7d99f0d64b62

> **18+** 仅供成年人管理自己的成人内容馆藏。仓库不含媒体或站点数据；连接外部站点需有相应账号和访问权。

## 能做什么

- **本地、网盘一起看**：硬盘与已挂载的 115、PikPak、OneDrive 等网盘汇成一个馆藏。
- **播放墙挑片**：拖动全屏封面墙，点开原位播放；同一番号的不同版本与分卷集中切换。
- **播放器字幕**：加载本地字幕，按番号搜索 SubtitleCat 简繁中文字幕并选择加载，调整字体、字号、颜色与背景。在线搜索无需 API Key，来源可能包含机翻。
- **接手已有收藏**：直接读取 NFO 和海报，缺少的标题、女优、厂牌与封面可从多个来源补齐，保留手动修改。
- **跨站关注**：同一创作者在 FANBOX、Patreon、Kemono 等站点的更新汇到一起，同一作品合成一张卡。
- **追新作、找想看的**：按女优订阅新作，按口味发现作品，用「想要」清单留住待找的片子。
- **云下载**：按番号查找资源或粘贴磁力，提交到 115 或 PikPak，落地后自动整理入库。
- **浏览器添加 JAV**：在 JavDB、MissAV、Jable 等站点识别或选中番号，一键交给 Peach 云下载入库。[用户脚本](https://github.com/peach-mitao/peach-userscript)独立维护，见[安装与配对](docs/JAV_BROWSER.md)。
- **口味**：结合观看、反馈、馆藏、浏览历史、书签与关注关系分析偏好。一次读取本机浏览器的历史和书签，也可导入 HTML 书签或 Chromium Bookmarks JSON；来源可停止读取或删除。见[口味数据来源](docs/TASTE_SOURCES.md)。

观看记录、收藏和设置保存在本机。扫描不动原文件；手动整理先预览，可撤回上一批。

扫描、关注更新和新作资料采集会保存进度，应用重启后继续处理未完成的项目。恢复范围见[断点续跑](docs/OPERATIONS.md#长时任务断点续跑)。

「发送版本统计与错误诊断（推荐）」默认勾选，可在安装、首次设置或设置页取消。两类技术事件由同一开关控制，已保存的关闭选择会保留。启用后向 Sentry 发送页面列出的技术字段，不自动上传完整日志、诊断 ZIP、媒体信息或观看记录。见[远程诊断说明](docs/DIAGNOSTICS.md#可选远程诊断)。

馆藏与口味明细上传在安装器和设置页另设独立选项，默认关闭。设置页先展示完整字段与本机预览，经明确同意后，每周上传作品、标签、评分、观看汇总及全部偏好维度的明细；不含账号、设备或安装标识。明细仍有跨次关联与再识别风险，接收服务可见连接 IP。见[馆藏与口味群体研究](docs/DIAGNOSTICS.md#馆藏与口味群体研究)。

## 截图

[在线演示](https://demo.peach.video) 可直接体验搜索、筛选和资料页，操作不会保存。点击截图查看原图。

<table>
  <tr>
    <td width="50%"><a href="https://peach.video/assets/screenshots/home-20261014.png" target="_blank" rel="noopener"><img src="https://peach.video/assets/screenshots/home-20261014.webp" alt="馆藏：首页筛选与作品卡片" width="600"></a></td>
    <td width="50%"><a href="https://peach.video/assets/screenshots/profile-20261014.png" target="_blank" rel="noopener"><img src="https://peach.video/assets/screenshots/profile-20261014.webp" alt="女优页：人像、资料与全部作品" width="600"></a></td>
  </tr>
  <tr>
    <td align="center">馆藏：按人物、来源和标签找片</td>
    <td align="center">女优页：资料、别名和全部作品</td>
  </tr>
  <tr>
    <td><a href="https://peach.video/assets/screenshots/follow-20261014.png" target="_blank" rel="noopener"><img src="https://peach.video/assets/screenshots/follow-20261014.webp" alt="关注：创作者导航与图片更新" width="600"></a></td>
    <td><a href="https://peach.video/assets/screenshots/stats-20261014.png" target="_blank" rel="noopener"><img src="https://peach.video/assets/screenshots/stats-20261014.webp" alt="统计：馆藏、存储与内容分布" width="600"></a></td>
  </tr>
  <tr>
    <td align="center">关注：创作者的跨站更新</td>
    <td align="center">统计：片子存在哪、看了多少</td>
  </tr>
  <tr>
    <td colspan="2"><a href="https://peach.video/assets/screenshots/wall-20261014.png" target="_blank" rel="noopener"><img src="https://peach.video/assets/screenshots/wall-20261014-readme.webp" alt="播放墙：全屏作品封面与浏览控件" width="1200"></a></td>
  </tr>
  <tr>
    <td colspan="2" align="center">播放墙：拖动挑片，原位播放</td>
  </tr>
</table>

## 下载与使用

### Windows

1. 从 [Releases](https://github.com/peach-mitao/peach/releases) 下载完整安装包 `Peach-<版本>-windows-x64-setup.exe`，双击安装，无需管理员权限；也可下载完整免安装包，解压后运行 `Peach.exe`。
2. 浏览器打开首次设置页后，选择媒体目录和访问范围。
3. 开始扫描，随后在浏览器里浏览和播放。

完整安装包携带媒体工具，可离线安装；轻量安装包体积更小，安装时按需下载工具。

测试版尚未签名。若 Windows 提示「已保护你的电脑」，确认来自本项目的 Release，再点「更多信息 → 仍要运行」。安装、更新和故障排查见 [Windows 使用说明](docs/TESTING_DESKTOP.md)。

### macOS 本机构建

macOS 可在本机构建独立 `.app` 与 DMG，运行不需要 Python、源码或另一台电脑。构建与安装见 [macOS 独立测试包](docs/OPERATIONS.md#macos-独立测试包)。

发版流程分别生成 Apple Silicon（`macos-arm64.dmg`）与 Intel（`macos-x86_64.dmg`）测试包；可下载版本以 [Releases](https://github.com/peach-mitao/peach/releases) 的实际资产为准。在「关于本机」确认芯片，打开对应镜像并将 Peach 拖入「应用程序」。测试包未完成 Apple 公证，媒体工具需另行准备。

### 从源码运行（Windows、macOS）

需要 Git、uv 和 Python 3.14 或更高，步骤见[源码运行](docs/OPERATIONS.md#从源码运行windowsmacos)。

### Docker（VPS / NAS）

部署步骤与支持范围见 [Docker 部署](docs/DOCKER.md)。

## 常见问题

- **会改我的文件吗？** 扫描、补资料不碰原文件。手动整理会改名或移动；清空回收站会删除文件，资源同步中的清理会删除空目录，均需确认。
- **支持哪些网盘？** 通过 CloudDrive2 等工具挂载为本地目录的网盘，详见[网盘挂载](docs/CLOUDDRIVE.md)；云下载支持 115 和 PikPak，登录令牌保存在本机。
- **手机上怎么看？** 首次设置时允许同一局域网的设备访问，手机连同一网络，打开设置页给出的地址，并设置访问密码。
- **数据存在哪？** 本机的 `peach-data` 文件夹；Windows 版默认位于 `%LOCALAPPDATA%\Peach\peach-data`。

## 问题反馈

先查看[用户反馈](https://github.com/peach-mitao/peach/issues)，或[提交问题](https://github.com/peach-mitao/peach/issues/new/choose)，附上版本、操作步骤、预期与实际结果。截图请遮掉凭据、局域网地址和完整路径，不要上传数据库或媒体；安全问题按[安全政策](SECURITY.md)私下报告。

## 文档

[运行与配置](docs/OPERATIONS.md) · [来源采集](docs/SOURCING.md) · [外部播放器](docs/EXTERNAL_PLAYERS.md) · [变更日志](CHANGELOG.md)

界面语言、StashDB 与播放选项：[功能变更](docs/CUSTOM-CHANGELOG.en.md) · [测试包使用说明](TEST-PACKAGE.en.md) · [StashDB 配置](docs/STASHDB.md)

扫描与采集提供停止按钮，已完成的工作会保留。关闭 StashDB 作品图片时，自动采集只匹配已有演员与厂牌；文件名识别与作品演员纠正的用途见配置说明。

数据管理的默认入口为「扫描全部（查找新增）」：遍历目录登记文件，仅对本趟新增影片读取资料、探测媒体、生成缺少的预览与执行 StashDB 匹配。没有新增影片时直接结束。下拉菜单的「扫描全部（完整扫描）」经确认后处理所有影片，保留已保存资料、图片与历史；已有可用预览继续复用。仅补全资料、仅生成预览与失败重试仍可单独执行。扫描期间仍会统计整个目录中的文件；这项目录发现不读取每个视频内容。本机根可读时沿用缺失文件标记，远程来源沿用资源同步对账。

演员页支持右侧资料与手工编辑，年龄按出生日期计算，别名保留名字内部空格。「来源与订阅 → StashDB」提供演员与厂牌独立重新同步，直接读取现有实体，不搜索作品。

参与开发：[开发约定](AGENTS.md) · [测试与依赖](docs/TESTING.md)

## 相关项目

感谢 [amane](https://github.com/sqzw-x/amane)、[Gfriends](https://github.com/gfriends/gfriends)、[CloudDrive2](https://www.clouddrive2.com/) 等项目，完整致谢与复用说明见[复用清单](docs/REUSE.md)。

## Star 历史

<a href="https://www.star-history.com/?repos=peach-mitao%2Fpeach&amp;type=date&amp;logscale=&amp;releases=&amp;legend=top-left">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=peach-mitao/peach&amp;type=date&amp;theme=dark&amp;logscale&amp;legend=top-left">
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=peach-mitao/peach&amp;type=date&amp;logscale&amp;legend=top-left">
    <img alt="Peach Star 历史" src="https://api.star-history.com/svg?repos=peach-mitao/peach&amp;type=date&amp;logscale&amp;legend=top-left">
  </picture>
</a>

## 许可证

[AGPL-3.0-or-later](LICENSE) · Copyright (C) 2026 longmeidao。第三方组件保留各自的许可证。

## 演员性别与全屏快进反馈

演员名册的「演员性别」菜单支持多选，并在本浏览器保存；首页等页面的随机演员沿用同一筛选。未取得性别的演员归「未知」，默认显示全部。StashDB 的「重新同步演员」会更新性别，手工资料覆盖仍保留。全屏播放时按快进／快退快捷键或手势，顶部中央短暂显示目标播放位置、总时长和进度条。

## 目录发现与浏览偏好

媒体目录支持父目录和子目录分别配置。每行的「扫描更新」控制数据管理手工扫描和自动扫描的新增文件发现；父目录遍历跳过单独配置的子目录，子目录按自己的开关处理。关闭开关保留已有馆藏、图片和历史。自动重扫间隔默认 0 小时，表示不自动扫描；填写 1–8760 小时后按该间隔执行「查找新增」，手工扫描完成也会重设该目录时钟。

手机播放器在画面右半侧双击执行小步快进，左半侧双击执行小步快退，沿用各自保存的步长。Following 的 RSS 菜单可多选订阅源，分页只统计所选来源，并在本浏览器保留选择；「全部 RSS 订阅源」恢复显示所有来源。

## 作品资料编辑与重新匹配

数据管理 → 人工复核 → 演员合并提供名字与别名相似建议，涵盖姓名后混入作品标题的情况。点击演员可查看全部候选、作品数、头像与相似原因；支持全选、取消全选、逐项选择，并可修改合并后的规范名。提交前逐组确认，只合并选中的身份，来源身份冲突的候选单独复核。

可勾选演员卡片旁的复选框，选择多个建议组分别自动合并，各组保留自己的演员身份。「忽略选中的组」忽略这些组的全部候选，包括来源冲突项；也可忽略单条候选，再从「显示已忽略的演员建议」恢复。忽略项不参加批量自动合并。

手机播放器在折叠、展开及影院视图保留独立全屏按钮，优先使用浏览器原生全屏或 iOS 视频全屏；不可用时填满浏览器窗口。关注页「刷新全部」等待普通来源和 RSS 检查都结束才报告合计结果。

时间轴设置可选择重新生成全部，或只补缺失及间隔更长的缩略图；例如选择 10 秒时保留已有 5 秒图，更新 30 秒图。确认删除只清理时间轴产物并停止生成，保留媒体和作品封面。StashDB「重新同步作品」只请求已有场景绑定，补空字段和缺图，保留已有演员、详情及图片，并添加尚缺的场景标签；常规场景匹配也同步标签。

StashDB 场景标签同时写入作品展示和规范标签关系，可在全局标签页检索，并参与馆藏及观看口味证据。更新时迁移 `0051` 自动补齐已同步标签的规范关系，无需再次查询 StashDB；用户标签和来源归属保留。口味馆藏标签计数包含无预览图和竖屏视频，Peach 观看分数仍依据观看及反馈。

合并保留作品最多的实体标识，采用选定规范名，迁移作品关系、别名、来源引用、收藏及资料，并保留原名搜索。优先采用选定演员的头像，其他头像原件保留。每次操作在账本目录保存 SQLite 备份及合并记录。演员合并建议数量计入数据管理的人工复核总数。

「自动合并全部」覆盖整库高置信度的姓名包含、共同姓和名及已登记别名，跳过模糊拼写和来源身份冲突；候选彼此存在来源冲突时也跳过。执行前确认数量，并在数据库目录的 `actor-merge-history/` 保留完整 SQLite 备份、全部演员头像及本批差异；该目录不参与普通账本备份清退。批次历史中的「撤销演员合并」只恢复本批改动，保留无关播放历史；有关演员资料、关系或图片已被另行修改时拒绝撤销。批次历史随数据卷持久保存，适用于此按钮创建的批次。「隐藏仅含来源身份冲突的建议」按浏览器记忆，只影响列表显示。

作品详情的图标栏提供编辑与重新匹配入口。编辑可保存标题、原始标题、番号、发行日期、厂牌、系列和演员名单，并分别上传封面与缩略图。演员按完整名称逐行填写，也可用逗号或分号分隔；手工名单（包括空名单）受来源归属保护。图片只覆盖本作品的显示，不影响共用番号的其他文件。

作品重新匹配只运行所选作品的资料任务，沿用已配置来源、采集规则、置信度及复核队列。演员与厂牌标题旁的重新匹配按钮使用 StashDB 同步当前实体，保留手工演员资料；演员编辑按钮位于同一图标栏。

## NZB 与 SABnzbd

NZB 条目在下载按钮前显示 RSS 提供的大小与发布组；缺少可读大小时使用附件字节数换算。已保存条目在订阅刷新后补充这些信息。

Following 的 NZB 条目区分详情页与下载链接；DrunkenSlug 条目按发布 ID 显示缩略图，保留订阅中的原始 NZB 下载地址。Peach 配置 → 下载渠道 → SABnzbd 可填写服务器地址、完整 API 密钥与分类，保存后测试连接。Docker 中须填写 Peach 容器可访问的地址；点击条目旁的「发送到 SABnzbd」将 NZB 加入 SABnzbd 队列，文件写入 SABnzbd 自己配置的目录。

SABconnect++ 使用浏览器中独立保存的 SABnzbd 配置；右键点击「下载 NZB」，使用扩展的发送动作。Peach 提供普通下载链接，不会自动安装扩展或向扩展传递 API 密钥。Newznab／DrunkenSlug 负责提供索引和 RSS，SABnzbd 负责下载。

下载渠道也支持 NZBGet：填写服务器地址、用户名、密码和分类，保存并测试连接后，NZB 条目显示「发送到 NZBGet」。空密码保留已存密码，「移除密码」撤销连接；文件写入 NZBGet 自己配置的下载目录。服务器地址可使用容器服务名与端口，也可填写含反向代理前缀的地址，Peach 自动补齐 `/jsonrpc`。

## 刷新关注与按忽略词重新匹配

Following 页的「刷新全部」同时检查关注来源与所有 RSS，旁边的上次更新时间来自已保存的来源检查记录。手机播放器的紧凑控制栏直接显示全屏按钮，触屏点击会显示控制栏，同侧双击仍使用小步跳转。

「媒体库与入库 → 文件名自动匹配」可逐行填写要忽略的字符、词或短语；匹配不区分大小写，不改动真实文件名。「重新匹配受影响的文件名」保存设置后，仅重建文件名含任一忽略词的已有影片的演员／厂牌自动归属，保留手工归属。

StashDB 的忽略词旁提供独立的重新匹配动作：仅对文件名含忽略词的影片重新检索，包括已有匹配与先前失败项，不受「仅新增」与「跳过失败」限制；图片与演员归属选项照常生效。关闭作品图片时仍只匹配演员与厂牌，不搜索作品。两种动作都不发现文件、不生成预览，进度与停止沿用数据管理中的统一任务。
