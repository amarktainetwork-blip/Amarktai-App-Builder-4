# Multi-stage build for the React frontend
FROM node:20-alpine AS build

WORKDIR /app
ENV CI=true \
    GENERATE_SOURCEMAP=false

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# REACT_APP_BACKEND_URL is baked in at build time.
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN npm run build

# --- runtime --------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
