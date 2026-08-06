# AI Eval Studio

智能问答对评估工作台前端（纯静态，无需构建，开箱即用）。

## 运行方式

本项目为纯静态前端，直接用浏览器打开 `index.html` 即可；若浏览器对本地文件的 fetch / 模块有限制，建议用任意静态服务器托管目录：

```bash
# 任选其一，在项目根目录执行
python3 -m http.server 8080
# 或
npx serve .
```

然后访问 `http://localhost:8080/index.html`。

无需 `npm install`、无需打包工具、无后端依赖。

## 第三方依赖

全部为前端资源，已随仓库提供（见根目录），无需联网安装：

| 依赖 | 文件 | 用途 | 版本说明 |
| --- | --- | --- | --- |
| Lucide Icons | `lucide.min.js` | 界面图标（`data-lucide` 渲染为 SVG） | 本地内置，约 0.4x 版本；如需升级到官方最新版，从 https://github.com/lucide-icons/lucide 下载 `lucide.min.js` 替换即可 |
| Chart.js | `chart.umd.min.js` | 看板图表 / KPI 趋势图 | 本地内置 UMD 构建（v4.x）；升级可从 https://www.chartjs.org 获取 `chart.umd.js` 替换 |
| 字体 Inter / Noto Sans SC | Google Fonts CDN（`<link>` 引入） | 界面排版 | 通过 `fonts.googleapis.com` 加载；**离线环境可忽略**，会自动回退到系统字体，不影响功能 |

> 说明：Lucide 与 Chart.js 均为本地文件，离线也能正常运行；仅 Google Fonts 走 CDN，缺失时仅影响字体外观。

## 目录结构

```
front-end/
├── index.html        # 页面结构
├── styles.css        # 样式（玻璃拟态 UI）
├── app.js            # 全部交互逻辑（无打包、无模块系统，IIFE 封装）
├── lucide.min.js     # 图标库（本地）
├── chart.umd.min.js  # 图表库（本地）
└── README.md         # 本文件
```

## 自定义与升级依赖

- **更新图标库**：下载新版 `lucide.min.js` 覆盖根目录同名文件，`app.js` 末尾会自动调用 `lucide.createIcons()` 重新渲染。
- **更新图表库**：覆盖 `chart.umd.min.js` 即可，注意 UMD 构建全局变量为 `Chart`。
- **移除 Google Fonts**：删除 `index.html` 顶部的 `<link>` 字体引用，界面会回退到系统默认字体。

## 浏览器要求

现代浏览器（Chrome / Edge / Firefox / Safari 近两个大版本），支持 CSS `backdrop-filter`、ES6 与 `fetch`。
