# Offer Radar MVP

这是一个面向 **Agent 开发 / 测试开发 / Agent 测试与质量** 面试准备的情报看板。

**完全自动化运行**：GitHub Actions 每天自动从公开渠道采集面经，你打开页面就能看积累的数据。

## 功能

- **自动采集**：每天从牛客等公开平台抓取面经帖子
- **结构化展示**：面试流程（几面、每面多久、问什么）一目了然
- **每日推送**：按优先级推送面试问题（AI测开 > AI产品经理 > Agent开发）
- **高频聚合**：自动统计高频问题标签
- **筛选过滤**：关键词搜索 + 岗位轨道筛选 + 自动排除实习/校招

## 使用方式

### 在线访问（推荐）

推送到 GitHub 后，开启 GitHub Pages：
1. 仓库 Settings → Pages → Source 选 “GitHub Actions”
2. 访问 `https://<你的用户名>.github.io/<仓库名>/`

GitHub Actions 会每天自动：
- 从牛客等平台采集新面经
- 提取面试流程信息
- 更新数据文件并部署

### 本地运行

```powershell
python -m http.server 8017
# 访问 http://localhost:8017
```

手动触发采集：

```powershell
python scripts/fetch_interviews.py
```

## 数据来源

- **牛客网**：公开面经讨论帖，无需登录
- **DuckDuckGo 搜索**：发现相关帖子链接
- 不绕过登录/验证码，不访问需要登录态的内容

## 项目结构

```
├── .github/workflows/
│   ├── daily-fetch.yml      # 每天定时采集
│   └── deploy-pages.yml     # 部署到 GitHub Pages
├── data/
│   ├── interview-events.json  # 面经事件库
│   └── daily-questions.json   # 每日推送问题
├── scripts/
│   └── fetch_interviews.py    # 采集脚本
├── src/
│   ├── app.js              # 前端逻辑
│   └── styles.css          # 样式
└── index.html              # 入口页面
```
