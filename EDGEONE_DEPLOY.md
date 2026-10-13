# 王多鱼看板 · EdgeOne Pages 部署配置说明

本仓库已通过改造，使生成的完整 `index.html` 自动提交回 `main` 分支，供腾讯云 EdgeOne Pages 检出部署。

## 部署方式（推荐）：源码托管 / 导入 Git 仓库

1. 登录 https://console.cloud.tencent.com/edgeone/pages
2. 创建项目 → 选择「导入 Git 仓库」
3. 授权 EdgeOne 访问你的 GitHub，选择仓库 `wwww1998/rotation-monitor`
4. 配置构建：
   - **构建命令(Build command)**：留空（本项目为纯静态单文件，无需构建）
   - **输出目录(Output directory)**：`public`
     > 因为网站文件位于仓库 `public/` 目录下，`index.html` 在内，EdgeOne 会以该目录为站点根。
5. 点击「开始部署」，部署完成后获得临时域名
6. 验证：访问临时域名应显示「科技红利轮动策略 · 每日监控」页面

## 每日自动更新

- 本仓库的 GitHub Actions（`.github/workflows/daily_update.yml`）按固定时点运行，共 14 次/天：
  - 北京时间 08:00（晨间）
  - 北京时间 15:30、16:05、16:35、17:05、17:35、18:05、18:35、19:05、20:05、21:05、22:05、23:05、次日 00:05（收盘后密集重试）
- **为什么排这么密**：GitHub 免费版的定时任务本身不可靠——实测延迟可达 4–7 小时且存在丢跑，而收盘后（北京时间 15:00 之后）正是其负载高峰、最容易被跳过。多排固定时点是为了提高「至少有一次跑成」的命中率；每次运行都会重新生成并提交页面，重复运行无副作用。
- 另有 `watchdog.yml` 兜底：北京时间 15:00–23:40 每 20 分钟检查一次页面更新时间，若未按当日收盘刷新，则自动补触发本工作流。
- Actions 生成最新页面后，会把完整 `index.html` 自动 commit + push 回 `main` 分支
- EdgeOne Pages 检测到 `main` 分支有新的 push 后，即自动重新构建部署 → 网站数据自动刷新

> 注意：需确认 EdgeOne Pages 的「自动部署」开关已开启（对推送自动触发构建）。

## 绑定你自己的域名（如 wangduoyu88.cn）

1. 在 EdgeOne Pages 项目详情 →「域名管理/自定义域名」添加你的域名
2. 平台会分配一条 CNAME 记录值，形如 `xxx.edgeone.site`
3. 到你的域名注册商（腾讯云/阿里云等）DNS 解析添加：
   - 记录类型：`CNAME`
   - 主机记录：`@`（主域名）与 `www`（www 子域名）
   - 记录值：粘贴 EdgeOne 分配的 CNAME 地址
   - TTL：默认 600
4. 等待生效（几分钟到几小时），EdgeOne 自动检测 CNAME 后自动签发免费 HTTPS 证书

## 文件说明

- `public/index.html` — 网站唯一入口（约 3MB 自包含单文件，含全部样式/脚本/图表数据）
- `.github/workflows/generate_page.py` — 数据抓取 + 策略回测 + 页面生成脚本（GitHub Actions 每日运行）
- `.github/workflows/daily_update.yml` — 定时触发器，已扩展「提交 index.html 回 main」步骤

## 故障排查

| 现象 | 排查 |
|---|---|
| 部署后页面空白/只有文字 | 确认输出目录为 `public`，且 index.html 完整可打开 |
| 数据不更新 | 检查 GitHub Actions 是否运行成功、EdgeOne「自动部署」是否开启、域名缓存（强制刷新/加 ?v=2） |
| 手机/浏览器看到旧数据 | EdgeOne 边缘缓存：刷新页面或稍等 CDN 失效 |

---

## 多站整合（导航首页方案）

当前您 GitHub 账号下有 5 个独立数据看板仓库，均适合用 **子域名+导航首页**方式整合。每个仓库对应一个子域名，独立 EdgeOne 项目，导航首页作为总入口：

```
 wangduoyu88.cn (主域名)
  ├─ rotation.wangduoyu88.cn  →  rotation-monitor (科技红轮动看板)
  ├─ etf.wangduoyu88.cn        →  national-team-etf-flow (国家队 ETF 流向)
  ├─ fp.wangduoyu88.cn       →  earl-etf-dashboard (EarlETF 图看板, fp)
  └─ dividend.wangduoyu88.cn   →  dividend-dashboard (红利指数回测看板)
```

### 操作步骤（按仓库逐个创建项目）

每个仓库创建步骤：

1. 在 EdgeOne Pages → **新建项目** → 导入 Git 仓库，选择对应仓库
2. **构建命令**留空 → **输出目录**：
   - `rotation-monitor` → `public`
   - 其他 (`national-team-etf-flow` / `earl-etf-dashboard` / `dividend-dashboard`) → **根目录 `.`**（因为 index.html 在仓库根）
3. 开始部署，部署后获得临时域名 → 自定义域名绑定 → 绑定对应子域名（如 `rotation.xxx.cn`）
4. 导航首页 `portal.html`（已生成）绑定到你的主域名 `xxx.cn`

> 所有子站都支持子路径挂载，无需修改代码——它们的资源引用都是相对路径，不依赖绝对路径。


---

## 一个仓库含多张网页怎么处理？

**核心原则：一个仓库 = 一个 EdgeOne 项目 + 一个子域名，仓库里的所有 ".html" 文件部署后自动全部上线**，用"子路径"访问，不需要为每张网页单独建项目。

各仓库上线后的完整地址：

- rotation.wangduoyu88.cn/ —— public/ 下只有 index.html 一张，入口即首页
- etf.wangduoyu88.cn/ —— 只有 index.html，入口即首页
- fp.wangduoyu88.cn/ —— /（index.html）+ /anchor_v2.html
- dividend.wangduoyu88.cn/
  - /dividend_dashboard.html（总回测）
  - /dividend_dashboard_yearly.html（年度）、/dividend_dashboard_yearly_1y.html（年度1年）
  - /dividend_dashboard_1y.html（1年）、/dividend_dashboard_3y.html（3年）、/dividend_dashboard_5y.html（5年）
  - /dividend_dashboard_roll.html（滚动）、/dividend_dashboard_stop12.html（止损12%）

说明：EdgeOne Pages 部署一个仓库时，输出目录内的所有静态文件都会发布到对应 URL 路径。只要资源用相对路径（./xxx.js）或 CDN 绝对外链，就能在任意子路径正常工作。已逐仓核查，dividend-dashboard / national-team-etf-flow / earl-etf-dashboard 均无绝对 "/" 路径引用，可直接以根目录发布。

导航首页 public/portal.html 已把上述全部子页面做成链接，打开主域名即可一键直达任意网页。
