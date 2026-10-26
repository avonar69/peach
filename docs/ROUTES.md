# 页面路由

「浏览与播放」的 `betaFastVideo`、`betaFastUI` 是当前浏览器的默认关闭偏好。普通本地 `GET/HEAD /stream` 可携带 `beta_fast=true` 请求五分钟私有缓存，仍要求鉴权并保持 Range；其他响应策略不变。客户端只为非计费本地片源附加此参数。实验行为及验证范围见[实验性能选项](PERFORMANCE.md)。

`/follow` 的「全部」在无创作者、来源、题材、标签或时长筛选的视频视图中展示 RSS 更新，复用 RSS 图片、预览、下载入口及分页；`/api/follow` 返回 `rss_count` 供总数展示。RSS 配置仍在 `/subscriptions?tab=rss`。

`POST /api/rss/source` 的 `action=schedule` 接受来源 `id`、布尔 `enabled` 与整数 `interval_minutes`，范围 15–10080 分钟。读接口返回每个来源的开关、间隔与下次检查时间，默认自动开启、360 分钟；手工检查包含关闭自动更新的来源。

RSS 条目中的 `images.main` 是主缩略图，`images.previews` 是带独立 `src` 与 `href` 的预览数组。`POST /api/rss/source` 的 `action=filter` 接收来源 `id` 和布尔 `hide_unsupported`，读取来源时返回该偏好；筛选只影响显示，准备下载仍使用原始 `link_index`。

`/subscriptions?tab=rss` 展示 RSS 下载订阅与新条目，`/settings/downloads` 配置 AllDebrid 和 Real-Debrid。`GET /api/rss` 分页返回条目、来源和本机任务；`POST /api/rss/{source,check,resolve,download,cancel}` 分别管理来源、更新列表、准备链接、目录下载和取消。链接准备只接受已保存的 RSS 条目与链接序号。渠道配置通过 `GET /api/configuration/debrid` 和 `POST /api/configuration/debrid/{provider}/{settings,check}`，不返回密钥。全部接口要求登录，写操作检查同源与只读状态，渠道配置沿用配置页访问边界。

渠道设置读写整数 `max_concurrent_downloads`（每个渠道默认 3，范围 1–10），限制服务端同时传输的文件数。`POST /api/rss/resolve` 可传布尔 `auto_download` 保存下载意图，单文件链接就绪后自动进入目录下载队列；多文件结果保留文件选择。准备链接使用独立单槽，等待中的传输在空位出现时继续。浏览器下载不受服务端并发设置控制。

`GET /api/rss` 接收 `offset` 与 `limit`，每页默认 20，接口将数量限制在 1–100。下载快照以 `parent_id`、`file_index` 与文件的 `download_id` 关联链接准备和传输，完整保留结束状态。`POST /api/rss/clear-finished` 将已结束且没有待办导入的下载标为 `dismissed`；文件、历史凭据和重试依据保留，写者与同源门槛适用。

列表使用一层路径，详情使用两层路径。查询参数表达筛选、排序与播放上下文；名称只用于展示和检索。

## 详情对象

| 对象 | 规范地址 | 身份 |
| --- | --- | --- |
| 资产 | `/assets/:id` | ledger 中的一条媒体记录；不同文件版本有各自 ID |
| 作品 | `/works/:code` | 规范番号；一个作品可对应多个馆藏资产 |
| 关注条目 | `/posts/:id` | 关注来源的一条帖子，包含视频或图片 |
| 艺人 | `/performers/:id` | `performer` 实体，含女优等艺人 |
| 厂牌、片商 | `/studios/:id` | `studio` 实体；资料按厂牌与上级片商关系展示 |
| 创作者 | `/creators/:id` | `creator` 实体，含 FC2 卖家与动画作者 |
| 事务所 | `/agencies/:id` | `agency` 实体 |
| 系列 | `/series/:id` | `series` 实体 |
| 本地标签 | `/tags/:id` | `tag` 实体；聚合相关资产与图片 |

数字 ID 不包含名字。实体改名沿用同一地址；合并 ID 跳到最终身份。来源中的人物或厂牌没有本地身份时只显示名称。

作品路径的番号使用规范形式，例如 `/works/ABP-968`。资产和帖子使用正整数 ID。不存在或种类不匹配的实体 ID 返回 404。

## 浏览入口

| 地址 | 用途 |
| --- | --- |
| `/` | 全部馆藏，含本地硬盘与已挂载网盘；新作行使用作品详情地址 |
| `/?browse=folders` | 按原目录浏览；`folder` 指定目录，`folder_recursive=0` 只看当前层 |
| `/?jav=1` | JAV 馆藏 |
| `/jav?tab=discover` | JAV 探索；`scope=library` 看馆藏，`scope=external` 看外部发现 |
| `/jav?tab=wants` | 想要的作品 |
| `/follow` | 关注更新；作者、来源、标签和观看状态使用查询参数 |
| `/wall` | 视频播放墙 |
| `/immerse` | 沉浸浏览；`id` 指定起始资产 |
| `/performers` | 艺人名册；动画作者通过 `category=animation` 浏览 |
| `/studios` | 厂牌、片商名册 |
| `/creators` | FC2 卖家名册；资料对象属于创作者 |
| `/agencies` | 事务所名册 |
| `/tags` | 本地或在线标签；在线标签通过关注页筛选 |
| `/playlists` | 播放列表 |
| `/unseen` | 没看过 |
| `/watch-later` | 稍后看 |
| `/flagged` | 已标记 |
| `/junk-files` | 垃圾文件 |
| `/trash` | 回收站 |

探索页将搜索词 `q`、标签 `tag`、排序 `sort`、方向 `dir` 与范围 `scope` 保存在地址中。点开详情和退出沿用原列表、滚动与筛选状态。

系列资料可直达；没有独立系列索引页面。

## 播放上下文

| 地址示例 | 上下文 |
| --- | --- |
| `/assets/30741?playlist=7` | 播放列表 7 |
| `/assets/30741?mix=30740` | 以资产 30740 为起点的 Mix |
| `/assets/30741?parts=30740` | 资产 30740 所在分卷组 |
| `/assets/30741?editions=30740` | 资产 30740 所在版本组 |

路径始终标识当前资产。换条更新 ID，队列键标识来源。复制播放地址时保留当前时间与队列上下文。

## 设置与管理

| 地址 | 用途 |
| --- | --- |
| `/settings`、`/settings/appearance` | 外观与导航 |
| `/settings/playback` | 浏览与播放 |
| `/settings/jav` | JAV 与新作 |
| `/settings/search` | 搜索与推荐 |
| `/settings/content` | 内容显示 |
| `/settings/library` | 媒体库与入库 |
| `/settings/subscriptions` | 来源与订阅参数 |
| `/settings/downloads` | 下载渠道 |
| `/settings/network` | 网络与访问 |
| `/settings/maintenance` | 应用与维护 |
| `/settings/diagnostics` | 系统诊断：系统检查、库健康与来源会话 |
| `/subscriptions` | 关注管理：关注列表、添加关注、JAV 订阅源 |
| `/sources` | 来源和凭证：采集来源、访问方式与凭据状态 |
| `/tasks` | 任务中心与云下载进度 |
| `/stats` | 统计 |
| `/taste` | 口味分析 |
| `/review` | 人工复核 |
| `/data-cleanup` | 数据管理 |
| `/duplicates` | 重复文件 |
| `/quality-goals` | 高清版目标 |
| `/login` | 登录 |

设置分区可直接打开、刷新和用浏览器前进后退。偏好面板从当前页面打开时保留背景；配置分区复用配置页及其权限检查。配置分类导航停在搜索栏下方，切换分类时显示所选分区的开头。

## 兼容地址与服务接口

| 兼容地址 | 规范去处 |
| --- | --- |
| `/item/:id` | `/assets/:id` |
| `/jav/movie/:code` | `/works/:code` |
| `/follow/item/:id` | `/posts/:id` |
| `/mix/:seed/:item`、`/parts/:seed/:item`、`/editions/:seed/:item` | `/assets/:item` 加相应队列参数 |
| `/playlists/:playlist/:item` | `/assets/:item?playlist=:playlist` |
| 实体的姓名、别名路径 | 对应数字 ID 地址 |
| `/activity` | `/tasks` |
| `/scraping` | `/sources` |
| `/follow-manage` | `/subscriptions` |
| `/configuration` | `/settings/library` |
| `/diagnostics` | `/settings/diagnostics` |
| `/resource-sync` | `/data-cleanup#resource-sync` |

兼容跳转保留查询参数；后退前进的背景信息留在历史条目中。索引尾斜杠跳到无尾斜杠路径。

`/api/*`、`/stream`、`/follow-stream`、封面、图片及其他媒体端点使用各自的服务契约。实体只读接口 `/api/entity`、`/api/photos` 支持 `kind` 加 `id`，也接受 `kind` 加 `name`。鉴权与本机写入权限由服务端检查。

启用接口文档时，`/docs`、`/docs/oauth2-redirect` 和 `/openapi.json` 是服务文档入口；首次运行表单由未配置状态下的首页展示。

### 演员资料与实体同步

`POST /api/actor-details` 接受 `entity_id` 与 `values`，返回保存后的 `actor_details`；`GET /api/entity` 在演员响应中提供同一资料。字段值为空字符串表示手工留空，`null` 表示使用来源值。写入沿用鉴权、同源与只读端门槛。

`POST /api/library-processing` 的 `stashdb_actors` 与 `stashdb_studios` 阶段只同步当前演员或厂牌，沿用任务状态查询、暂停、恢复与停止接口；不扫描媒体或查询作品。

`POST /api/library-processing` 未提供 `stage` 时使用 `find_new`：目录发现完成后，将本趟新增视频标识固定为处理范围，后续本地资料、探测、预览、候选结算、StashDB 和后继任务均沿用该范围；新增集合为空时直接完成。显式 `stage=all` 处理全库，其他阶段与定向重试保留各自范围。扫描断点持久保存起始资产标识水位，续跑沿用该水位，同秒发起的独立扫描互不混入新增集合。

`POST /api/rss/source` 的 `retention` 动作接收来源 `id`、`count` 与 `unit`（`days`／`months`／`years`）；`count=null` 表示永久保存，整数限制为 1 天至 100 年。`GET /api/rss` 的来源返回 `rss_retention_count` 和 `rss_retention_unit`，条目及关注总数均排除已合并或已到期内容。稳定身份映射保留以阻止重复或到期条目重新出现。

`GET /api/rss/jobs` 返回已鉴权的 debrid 任务、无密钥的渠道配置及只读状态，供常驻下载浮层观察。下载渠道设置支持布尔 `auto_import`；启用须配置媒体根内的下载目录。下载任务返回独立 `import_state`、`import_error` 和可选 `imported_asset_id`。`POST /api/rss/import` 接收完成下载的 `id` 以重试定向导入；已有取消接口同时支持取消待办导入。所有写操作沿用同源、鉴权及写者门槛。
