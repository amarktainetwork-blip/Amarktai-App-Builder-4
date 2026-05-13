# Production Settings Recovery

Encrypted provider settings are tied to `SETTINGS_ENCRYPTION_KEY`. If that key changes while the existing MongoDB `settings` collection still contains encrypted rows from the old key, those rows cannot be decrypted.

The app must not crash in this state. Runtime status endpoints now fall back to environment variables when possible and mark bad stored rows as `decrypt_failed`.

## Safe Cleanup

From the repo root on the VPS:

```bash
python scripts/cleanup_bad_settings.py --dry-run
python scripts/cleanup_bad_settings.py --backup-metadata /var/www/amarktai/settings-backup-metadata.json --delete-bad
```

The script:

- scans the configured Mongo database and `settings` collection
- never prints secret values
- reports counts by status
- optionally writes masked metadata
- deletes only undecryptable or malformed setting rows when `--delete-bad` is passed

## Key Rotation Rule

Do not generate a new `SETTINGS_ENCRYPTION_KEY` on an existing database unless you are intentionally rotating settings. Either keep the old key, or clear/re-save provider settings after running the cleanup script.

## Production Redeploy Checklist

1. Back up `.env` and optional masked settings metadata.
2. Confirm required values:

```bash
APP_ENV=production
JWT_SECRET=<32+ chars>
SETTINGS_ENCRYPTION_KEY=<existing Fernet key or intentional new key>
ADMIN_EMAIL=<email>
ADMIN_PASSWORD=<12+ chars>
GENX_API_KEY=<required>
BUILDS_STORAGE_ROOT=/var/www/amarktai/builds
CORS_ORIGINS=https://builder.amarktai.com
```

3. Optional provider values:

```bash
GITHUB_PAT=
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_CHAT=qwen3-max
QWEN_MODEL_CODE=qwen3-coder-plus
QWEN_MODEL_IMAGE=qwen-image-plus
QWEN_MODEL_VIDEO=qwen3-omni-flash
QWEN_MODEL_AUDIO=qwen3-asr-flash
BRAVE_SEARCH_API_KEY=
PIXABAY_API_KEY=
```

4. If decrypt failures appear:

```bash
python scripts/cleanup_bad_settings.py --dry-run
python scripts/cleanup_bad_settings.py --delete-bad
```

5. Rebuild and verify:

```bash
docker compose build
docker compose up -d
curl -s https://builder.amarktai.com/api/health | python3 -m json.tool
curl -s https://builder.amarktai.com/api/readiness | python3 -m json.tool
curl -s https://builder.amarktai.com/api/capabilities | python3 -m json.tool
curl -s https://builder.amarktai.com/api/builds
```

`/api/builds` is auth-gated. A 401/403 is correct when unauthenticated; 404 is not.
