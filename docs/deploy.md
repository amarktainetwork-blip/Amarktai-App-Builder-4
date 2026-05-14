# Deploy App Builder 4

The production VPS deploy path is `/var/www/amarktai/repo` and the live URL is `https://builder.amarktai.com`.

## Required Production Environment

```bash
APP_ENV=production
JWT_SECRET=<random value, at least 32 characters>
SETTINGS_ENCRYPTION_KEY=<Fernet key>
ADMIN_EMAIL=<admin email>
ADMIN_PASSWORD=<strong password, at least 12 characters>
GENX_API_KEY=<optional here if supplied through encrypted dashboard Settings>
GENX_BASE_URL=https://query.genx.sh/v1
BUILDS_STORAGE_ROOT=/var/www/amarktai/builds
CORS_ORIGINS=https://builder.amarktai.com
MONGO_URL=mongodb://mongo:27017
DB_NAME=amarktai_builder
```

`GENX_API_KEY` is required at runtime because builder agents cannot truthfully run without it. Production startup may use encrypted dashboard Settings for this provider key; readiness fails with a blocker if neither Settings nor environment provides a valid key.

## Recommended Providers

```bash
GITHUB_PAT=<private repo import and PR automation>
QWEN_API_KEY=<optional direct Qwen workflows>
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_CHAT=qwen3-max
QWEN_MODEL_CODE=qwen3-coder-plus
QWEN_MODEL_IMAGE=qwen-image-plus
QWEN_MODEL_VIDEO=qwen3-omni-flash
QWEN_MODEL_AUDIO=qwen3-asr-flash
BRAVE_SEARCH_API_KEY=<web research>
PIXABAY_API_KEY=<stock media>
```

Missing optional providers produce readiness warnings and disabled capabilities, not fake green states.

## Commands

```bash
cd /var/www/amarktai/repo
git fetch origin main
git checkout main
git pull --ff-only

mkdir -p /var/www/amarktai/builds/repos \
  /var/www/amarktai/builds/generated \
  /var/www/amarktai/builds/incomplete \
  /var/www/amarktai/builds/releases \
  /var/www/amarktai/builds/logs

chown -R admin:www-data /var/www/amarktai/builds
chmod -R 775 /var/www/amarktai/builds

python scripts/cleanup_bad_settings.py --dry-run

docker compose build
docker compose up -d
```

## Verify

```bash
curl -s https://builder.amarktai.com/api/health | python3 -m json.tool
curl -s https://builder.amarktai.com/api/readiness | python3 -m json.tool
curl -s https://builder.amarktai.com/api/capabilities | python3 -m json.tool
curl -s https://builder.amarktai.com/api/builds
```

Manual checks:

- login works
- Settings and New Build show the same provider truth
- `/api/builds` returns auth error when logged out, not 404
- landing-page build reaches coder and generates files
- preview renders generated output
- quality gate writes a report
