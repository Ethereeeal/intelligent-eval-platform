# AI Eval Studio — 纯静态前端容器化
# 项目为静态资源（index.html / styles.css / app.js / lucide.min.js / chart.umd.min.js），
# 无需构建、无后端依赖，用 nginx 直接托管。
FROM nginx:1.27-alpine

# 移除默认站点，放入工作室静态资源
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/studio.conf
COPY . /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
