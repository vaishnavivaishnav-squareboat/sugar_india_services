// /**
//  * PM2 ecosystem for Dhampur Green backend (sugar_india_services)
//  * - Manages: API (uvicorn), Celery worker, Celery beat
//  * - Loads environment from `.env` via `source .env` and optionally activates `venv`.
//  * - Start with: `pm2 start ecosystem.config.js`
//  */

// module.exports = {
//   apps: [
//     {
//       name: "horeca-api",
//       // Use a shell so we can `source .env` and activate virtualenv if present
//       script: "bash",
//       args: "-lc 'source venv/bin/activate 2>/dev/null || true; set -a; [ -f .env ] && source .env; set +a; exec uvicorn main:app --host 0.0.0.0 --port 8001'",
//       cwd: __dirname,
//       exec_mode: "fork",
//       instances: 1,
//       autorestart: true,
//       watch: false,
//       max_restarts: 10,
//       error_file: "./logs/horeca-api-error.log",
//       out_file: "./logs/horeca-api-out.log",
//       log_date_format: "YYYY-MM-DD HH:mm Z",
//     },

//     {
//       name: "horeca-worker",
//       script: "bash",
//       args: "-lc 'source venv/bin/activate 2>/dev/null || true; set -a; [ -f .env ] && source .env; set +a; exec celery -A app.core.celery_app worker --loglevel=info --concurrency=2'",
//       cwd: __dirname,
//       exec_mode: "fork",
//       instances: 1,
//       autorestart: true,
//       watch: false,
//       max_restarts: 10,
//       error_file: "./logs/horeca-worker-error.log",
//       out_file: "./logs/horeca-worker-out.log",
//       log_date_format: "YYYY-MM-DD HH:mm Z",
//     },

//     {
//       name: "horeca-beat",
//       script: "bash",
//       args: "-lc 'source venv/bin/activate 2>/dev/null || true; set -a; [ -f .env ] && source .env; set +a; exec celery -A app.core.celery_app beat --loglevel=info'",
//       cwd: __dirname,
//       exec_mode: "fork",
//       instances: 1,
//       autorestart: true,
//       watch: false,
//       max_restarts: 10,
//       error_file: "./logs/horeca-beat-error.log",
//       out_file: "./logs/horeca-beat-out.log",
//       log_date_format: "YYYY-MM-DD HH:mm Z",
//     },
//   ],
// };

/**
 * PM2 ecosystem for Dhampur Green backend
 *
 * Handles:
 * - create venv if missing
 * - install requirements once (API app only)
 * - load .env
 * - run alembic upgrade head
 * - start FastAPI
 * - start Celery worker
 * - start Celery beat
 *
 * Start:
 * pm2 start ecosystem.config.js
 */

module.exports = {
  apps: [
    {
      name: "horeca-api",
      script: "bash",

      args: `-lc '
        cd /home/ubuntu/apps/sugar_india_services &&

        mkdir -p logs &&

        # Create virtualenv if missing
        [ -d venv ] || python3 -m venv venv &&

        # Activate venv
        source venv/bin/activate &&

        # Upgrade pip
        pip install --upgrade pip &&

        # Install dependencies (ONLY HERE)
        pip install -r requirements.txt &&

        # Load environment variables
        set -a
        [ -f .env ] && source .env
        set +a

        # Run DB migrations (ONLY HERE)
        alembic upgrade head &&

        # Start FastAPI
        exec uvicorn main:app --host 0.0.0.0 --port 8001
      '`,

      cwd: "/home/ubuntu/apps/sugar_india_services",
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

      args: `-lc '
        cd /home/ubuntu/apps/sugar_india_services &&

        # Ensure venv exists
        [ -d venv ] || python3 -m venv venv &&

        # Activate existing venv
        source venv/bin/activate &&

        # Load environment variables
        set -a
        [ -f .env ] && source .env
        set +a

        # Start Celery Worker
        exec celery -A app.core.celery_app worker --loglevel=info --concurrency=2
      '`,

      cwd: "/home/ubuntu/apps/sugar_india_services",
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

      args: `-lc '
        cd /home/ubuntu/apps/sugar_india_services &&

        # Ensure venv exists
        [ -d venv ] || python3 -m venv venv &&

        # Activate existing venv
        source venv/bin/activate &&

        # Load environment variables
        set -a
        [ -f .env ] && source .env
        set +a

        # Start Celery Beat
        exec celery -A app.core.celery_app beat --loglevel=info
      '`,

      cwd: "/home/ubuntu/apps/sugar_india_services",
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