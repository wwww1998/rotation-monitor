# 指数轮动策略 · 每日监控

基于 AKShare 数据的创业板指与红利低波指数轮动策略监控看板。

## 部署到 Render（免费）

1. **注册 Render 账号**  
   打开 https://render.com，用 GitHub 或 Google 账号注册。

2. **创建 GitHub 仓库**  
   ```bash
   # 在 GitHub 上新建一个仓库，然后：
   git init
   git add .
   git commit -m "init"
   git remote add origin https://github.com/你的用户名/rotation-monitor.git
   git push -u origin main
   ```

3. **在 Render 部署**  
   - 登录 Render → Dashboard → New → Web Service
   - 连接你的 GitHub 仓库
   - Render 会自动检测 `render.yaml`，按默认配置即可
   - 或手动选择：Runtime = Python, Build Command = `pip install -r requirements.txt`, Start Command = `python main.py`
   - 选择 Free 计划，Region 选 Singapore（亚洲访问更快）
   - 点击 Create Web Service

4. **等待部署完成**  
   Render 会自动构建并启动，约 3-5 分钟。完成后会分配一个 `https://xxx.onrender.com` 的域名。

5. **手机访问**  
   直接在手机浏览器打开 Render 分配的域名即可。

## 本地运行

```bash
pip install -r requirements.txt
python main.py
```

访问 http://localhost:8000

## 数据说明

- 数据来源：AKShare（新浪财经 / 中证指数官网）
- 创业板指代码：399006（新浪）
- 红利低波代码：H30269（中证指数）
- 缓存策略：每次请求缓存 5 分钟，避免频繁调用 API