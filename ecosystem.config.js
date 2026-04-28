/**
 * PM2 ecosystem for Dhampur Green backend (sugar_india_services)
 * - Manages: API (uvicorn), Celery worker, Celery beat
 * - Loads environment from `.env` via `source .env` and optionally activates `venv`.
 * - Start with: `pm2 start ecosystem.config.js`
 */

module.exports = {
  apps: [
    {
      name: "horeca-api",
      // Use a shell so we can `source .env` and activate virtualenv if present
      script: "bash",
      args: "-lc 'source venv/bin/activate 2>/dev/null || true; set -a; [ -f .env ] && source .env; set +a; exec uvicorn main:app --host 0.0.0.0 --port 8001'",
      cwd: __dirname,
      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      error_file: "./logs/horeca-api-error.log",
      out_file: "./logs/horeca-api-out.log",
      log_date_format: "YYYY-MM-DD HH:mm Z",
    },

    {
      name: "horeca-worker",
      script: "bash",
      args: "-lc 'source venv/bin/activate 2>/dev/null || true; set -a; [ -f .env ] && source .env; set +a; exec celery -A app.core.celery_app worker --loglevel=info --concurrency=2'",
      cwd: __dirname,
      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      error_file: "./logs/horeca-worker-error.log",
      out_file: "./logs/horeca-worker-out.log",
      log_date_format: "YYYY-MM-DD HH:mm Z",
    },

    {
      name: "horeca-beat",
      script: "bash",
      args: "-lc 'source venv/bin/activate 2>/dev/null || true; set -a; [ -f .env ] && source .env; set +a; exec celery -A app.core.celery_app beat --loglevel=info'",
      cwd: __dirname,
      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      watch: false,
      max_restarts: 10,
      error_file: "./logs/horeca-beat-error.log",
      out_file: "./logs/horeca-beat-out.log",
      log_date_format: "YYYY-MM-DD HH:mm Z",
    },
  ],
};

