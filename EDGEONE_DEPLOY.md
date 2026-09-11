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
6. 验证：访问临时域名应显示「科技红轮动策略 · 每日监控」页面

## 每日自动更新

- 本仓库的 GitHub Actions（`.github/workflows/daily_update.yml`）每天 5 次（北京时间 8:00/15:30/16:30/20:00/24:00）运行
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